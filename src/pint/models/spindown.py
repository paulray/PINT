"""Polynomial pulsar spindown."""
# spindown.py
# Defines Spindown timing model class
from __future__ import absolute_import, print_function, division
import numpy
import astropy.units as u
from astropy.time import Time
try:
    from astropy.erfa import DAYSEC as SECS_PER_DAY
except ImportError:
    from astropy._erfa import DAYSEC as SECS_PER_DAY

from . import parameter as p
from .timing_model import PhaseComponent, MissingParameter
from ..phase import *
from ..utils import time_from_mjd_string, time_to_longdouble, str2longdouble,\
    taylor_horner, time_from_longdouble, split_prefixed_name, taylor_horner_deriv
from pint import dimensionless_cycles
import pint.toa as toa


class Spindown(PhaseComponent):
    """A simple timing model for an isolated pulsar."""
    register = True
    category = 'spindown'
    def __init__(self):
        super(Spindown, self).__init__()
        self.add_param(p.floatParameter(name="F0", value=0.0, units="Hz",
                       description="Spin-frequency", long_double=True))
        self.add_param(p.prefixParameter(name="F1", value=0.0, units='Hz/s^1',
                       description="Spindown-rate",
                       unit_template=self.F_unit,
                       description_template=self.F_description,
                       type_match='float', long_double=True))
        self.add_param(p.MJDParameter(name="PEPOCH",
                       description="Reference epoch for spin-down",
                       time_scale='tdb'))

        self.phase_funcs_component += [self.spindown_phase,]
        self.phase_derivs_wrt_delay += [self.d_spindown_phase_d_delay,]

    def setup(self):
        super(Spindown, self).setup()
        # Check for required params
        for p in ("F0",):
            if getattr(self, p).value is None:
                raise MissingParameter("Spindown", p)

        # Check continuity
        F_terms = list(self.get_prefix_mapping_component('F').keys())
        F_terms.sort()
        F_in_order = list(range(1, max(F_terms)+1))
        if not F_terms == F_in_order:
            diff = list(set(F_in_order) - set(F_terms))
            raise MissingParameter("Spindown", "F%d"%diff[0])

        # If F1 is set, we need PEPOCH
        if self.F1.value != 0.0:
            if self.PEPOCH.value is None:
                raise MissingParameter("Spindown", "PEPOCH",
                        "PEPOCH is required if F1 or higher are set")
        self.num_spin_terms = len(F_terms) + 1
        # Add derivative functions
        for fp in list(self.get_prefix_mapping_component('F').values()) + ['F0',]:
            self.register_deriv_funcs(self.d_phase_d_F, fp)

    def F_description(self, n):
        """Template function for description"""
        return "Spin-frequency %d derivative" % n if n else "Spin-frequency"

    def F_unit(self, n):
        """Template function for unit"""
        return "Hz/s^%d" % n if n else "Hz"

    def get_spin_terms(self):
        """Return a list of the spin term values in the model: [F0, F1, ..., FN]
        """
        return [getattr(self, "F%d" % ii).quantity for ii in
                range(self.num_spin_terms)]

    def get_dt(self, toas, delay):
        """Return dt, the time from the phase 0 epoch to each TOA.  The
        phase 0 epoch is assumed to be PEPOCH.  If PEPOCH is not set,
        the first TOA in the table is used instead.

        Note, the phase 0 epoch as used here is only intended for
        computation internal to the Spindown class.  The "traditional"
        tempo-style TZRMJD and related parameters for specifying absolute
        pulse phase will be handled at a higher level in the code.
        """
        tbl = toas.table
        if self.PEPOCH.value is None:
            phsepoch_ld = time_to_longdouble(tbl['tdb'][0] - delay[0])
        else:
            phsepoch_ld = time_to_longdouble(self.PEPOCH.quantity)
        dt = (tbl['tdbld'] - phsepoch_ld) * u.day - delay
        return dt

    def spindown_phase(self, toas, delay):
        """Spindown phase function.

        delay is the time delay from the TOA to time of pulse emission
          at the pulsar, in seconds.

        This routine should implement Eq 120 of the Tempo2 Paper II (2006, MNRAS 372, 1549)

        returns an array of phases in long double
        """
        dt = self.get_dt(toas, delay)
        # Add the [0.0] because that is the constant phase term
        fterms = [0.0 * u.cycle] + self.get_spin_terms()
        with u.set_enabled_equivalencies(dimensionless_cycles):
            phs = taylor_horner(dt.to(u.second), fterms)
            return phs.to(u.cycle)

    def change_pepoch(self, new_epoch, toas=None, delay=None):
        """Move PEPOCH to a new time and change the related paramters.

        Parameters
        ----------
        new_epoch: float or `astropy.Time` object
            The new PEPOCH value.
        toas: `toa` object, optional.
            If current PEPOCH is not provided, the first pulsar frame toa will
            be treated as PEPOCH.
        delay: `numpy.array` object
            If current PEPOCH is not provided, it is required for computing the
            first pulsar frame toa.
        """
        if isinstance(new_epoch, Time):
            new_epoch = Time(new_epoch, scale='tdb', precision=9)
        else:
            new_epoch = Time(new_epoch, scale='tdb', format='mjd', precision=9)
        # make new_epoch a toa for delay calculation.
        new_epoch_toa = toa.get_TOAs_list([toa.TOA(new_epoch),],
                                          ephem=toas.ephem)

        if self.PEPOCH.value is None:
            if toas is None or delay is None:
                raise ValueError("`PEPOCH` is not in the model, thus, 'toa' and"
                                 " 'delay' shoule be givne.")
            tbl = toas.table
            phsepoch_ld = time_to_longdouble(tbl['tdb'][0] - delay[0])
        else:
            phsepoch_ld = time_to_longdouble(self.PEPOCH.quantity)
        dt = ((time_to_longdouble(new_epoch) - phsepoch_ld) * u.day)
        fterms = [0.0 * u.Unit("")] + self.get_spin_terms()
        # rescale the fterms
        for n in range(len(fterms) - 1):
            f_par = getattr(self, 'F{}'.format(n))
            f_par.value = taylor_horner_deriv(dt.to(u.second), fterms,
                                              deriv_order=n+1)
        self.PEPOCH.value = new_epoch

    def print_par(self,):
        result = ''
        f_terms = ["F%d" % ii for ii in
                range(self.num_spin_terms)]
        for ft in f_terms:
            par = getattr(self, ft)
            result += par.as_parfile_line()
        if hasattr(self, 'components'):
            p_default = self.components['Spindown'].params
        else:
            p_default = self.params
        for param in p_default:
            if param not in f_terms:
                result += getattr(self, param).as_parfile_line()
        return result

    def d_phase_d_F(self, toas, param, delay):
        """Calculate the derivative wrt to an spin term."""
        par = getattr(self, param)
        unit = par.units
        pn, idxf, idxv = split_prefixed_name(param)
        order = idxv + 1
        fterms = [0.0 * u.Unit("")] + self.get_spin_terms()
        # make the choosen fterms 1 others 0
        fterms = [ft * numpy.longdouble(0.0)/unit for ft in fterms]
        fterms[order] += numpy.longdouble(1.0)
        dt = self.get_dt(toas, delay)
        with u.set_enabled_equivalencies(dimensionless_cycles):
            d_pphs_d_f = taylor_horner(dt.to(u.second), fterms)
            return d_pphs_d_f.to(u.cycle/unit)

    def d_spindown_phase_d_delay(self, toas, delay):
        dt = self.get_dt(toas, delay)
        fterms = [0.0] + self.get_spin_terms()
        with u.set_enabled_equivalencies(dimensionless_cycles):
            d_pphs_d_delay = taylor_horner_deriv(dt.to(u.second), fterms)
            return -d_pphs_d_delay.to(u.cycle/u.second)