import numpy as np
import math
import cmath
from spec_pkg.constants import constants as const
from numba import jit, njit, prange
from spec_pkg.cumulant import cumulant as cumu

traj = np.loadtxt('traj1_tdm_s1.dat')
dipoles = traj[:,1:]
t2s_ind = 0

out = cumu.compute_polarized_tdm(dipoles, t2s_ind, 50, "parallel")

print(out.shape)
print(out[0])

