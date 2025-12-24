import numpy as np
import sys

# assumes original data is sampled every 0.5 fs

inf = sys.argv[1]
inc = int(sys.argv[2])
com = sys.argv[3]

odat = np.loadtxt(inf)
osampling = np.arange(len(odat))*0.5

print('# points: ',len(osampling[0::inc]))
print('new dt: ',osampling[0::inc][1])

np.savetxt('es_traj'+com+'.dat',odat[0::inc])

