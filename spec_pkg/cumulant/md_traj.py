#! /usr/bin/env python

import os.path
import numpy as np
import math
import cmath
from scipy import integrate
import time
from numba import jit
from spec_pkg.constants import constants as const
import spec_pkg.cumulant.cumulant as cumulant
import spec_pkg.cumulant.herzberg_teller as ht
import spec_pkg.nonlinear_spectrum.twoDES as twoDES

# Works
@jit
def ensemble_response_for_given_t(fluctuations,dipole_mom,mean,t):
	response_val=0.0
	icount=0
	while icount<fluctuations.shape[0]:
		jcount=0
		while jcount<fluctuations.shape[1]:
			response_val=response_val+(dipole_mom[icount,jcount])**2.0*cmath.exp(-1j*((fluctuations[icount,jcount]))*t)
			jcount=jcount+1
		icount=icount+1
	return response_val/(fluctuations.shape[0]*fluctuations.shape[1]*1.0)
	
# introduce artificial, constant SD for ensemble spectra. This can be treated as a convergence parameter to ensure smoothness
# for insufficient sampling
def construct_full_ensemble_response(fluctuations,dipole_mom, mean, max_t,num_steps,decay_const):
	response_func=np.zeros((num_steps,2),dtype=complex)
	tcount=0
	t_step=max_t/num_steps
	while tcount<num_steps:
		response_func[tcount,0]=tcount*t_step
		response_func[tcount,1]=ensemble_response_for_given_t(fluctuations,dipole_mom,mean,response_func[tcount,0])*cmath.exp(-1j*mean*tcount*t_step)*np.exp(-abs(tcount*t_step)/decay_const)
		tcount=tcount+1

	return response_func

def construct_full_cumulant_response(g2,g3,mean,is_3rd_order,is_emission):
	response_func=np.zeros((g2.shape[0],2),dtype=complex)
	counter=0
	while counter<response_func.shape[0]:
		response_func[counter,0]=g2[counter,0]
		if is_emission:
			if is_3rd_order:
				g3_temp=1j*g3[counter,1]
				response_func[counter,1]=cmath.exp(-1j*mean*g2[counter,0]-np.conj(g2[counter,1])-1j*np.conj(g3_temp))
			else:
				response_func[counter,1]=cmath.exp(-1j*mean*g2[counter,0]-np.conj(g2[counter,1]))
		else:
			if is_3rd_order:
				response_func[counter,1]=cmath.exp(-1j*mean*g2[counter,0]-g2[counter,1]-g3[counter,1])
			else:
				response_func[counter,1]=cmath.exp(-1j*mean*g2[counter,0]-g2[counter,1])

		counter=counter+1
	return response_func

# return dipole moment squared for all transitions 
def get_dipole_mom(oscillators,trajs):
	# compute fluctuations for each trajectory around the common mean
	dipole_moms=np.zeros((oscillators.shape[0],oscillators.shape[1]))
	icount=0
	while icount<trajs.shape[0]:
		jcount=0
		while jcount<trajs.shape[1]:
			dipole_moms[icount,jcount]=np.sqrt(oscillators[icount,jcount]/(trajs[icount,jcount]/const.Ha_to_eV)*3.0/2.0)
			jcount=jcount+1
		icount=icount+1

	return dipole_moms

def get_fluctuations(trajectories,mean):
	# compute fluctuations for each trajectory around the common mean
	flucts=np.zeros((trajectories.shape[0],trajectories.shape[1]))
	icount=0
	while icount<flucts.shape[0]:
		jcount=0
		while jcount<flucts.shape[1]:
			flucts[icount,jcount]=trajectories[icount,jcount]/const.Ha_to_eV-mean
			jcount=jcount+1
		icount=icount+1

	return flucts

# calculate the total mean of a batch of trajectory functions
def mean_of_func_batch(func):
	mean=0.0
	for x in func:
		for y in x:
			mean=mean+y
	mean=mean/(func.shape[0]*func.shape[1])
	sd=0.0
	skew=0.0
	for x in func:
		for y in x:
			sd=sd+(y-mean)**2.0
			skew=skew+(y-mean)**3.0

	mean=mean/const.Ha_to_eV
	sd=np.sqrt(sd/(func.shape[0]*func.shape[1])/const.Ha_to_eV)
	skew=(skew/const.Ha_to_eV)/((func.shape[0]*func.shape[1])*sd**3.0)

	return mean,sd,skew

# generate an array of trajectory functions from files
def get_all_trajs(num_trajs,name_list):
	traj1=np.genfromtxt(name_list[0])
	num_points=traj1.shape[0]
	trajs=np.zeros((num_points,num_trajs))
	traj_count=1
	while traj_count<num_trajs:
		traj_current=np.genfromtxt(name_list[traj_count])
		icount=0
		while icount<traj_current.shape[0]:
			trajs[icount,traj_count-1]=traj_current[icount,0]/const.Ha_to_eV
			icount=icount+1
		traj_count=traj_count+1

	return trajs


#-----------------------------------------------------------
# Class definitions

class MDtrajs:
	def __init__(self,trajs,oscillators,tau,num_trajs,time_step,stdout):
		self.num_trajs=num_trajs
		stdout.write('Building an MD trajectory model:'+'\n')
		stdout.write('Number of independent trajectories:   '+str(num_trajs)+'\n')
		self.mean,sd,skew=mean_of_func_batch(trajs)
		stdout.write('Mean thermal energy gap:    '+str(self.mean)+'  Ha'+'\n')
		stdout.write('Standard deviation of energy gap fluctuations: '+str(sd)+' Ha'+'\n')
		if abs(skew)>0.3: # check for large skewness parameter
			stdout.write('WARNING: Large skewness value of '+str(skew)+' detected in energy gap fluctuations.'+'\n')
			stdout.write('This means that the energy gap fluctuations are likely non-Gaussian in nature and low-order cumulant expansions might be unreliable!'+'\n'+'\n')

		self.fluct=get_fluctuations(trajs,self.mean)
		self.dipole_mom=get_dipole_mom(oscillators,trajs)
		self.dipole_mom_av=np.sum(self.dipole_mom)/(1.0*self.dipole_mom.shape[0]*self.dipole_mom.shape[1]) # average dipole mom
		self.dipole_reorg=0.0 # dipole reorganization and renormalized dipole moment
		self.dipole_renorm=0.0 # required for HT terms
		self.dipole_fluct=self.dipole_mom-self.dipole_mom_av # construct fluctuations of 
		# dipole mom needed for Herzberg Term
		stdout.write('Mean dipole moment: '+str(self.dipole_mom_av)+'  Ha'+'\n')
		
		self.time_step=time_step # time between individual snapshots. Only relevant
		# for cumulant approach. In the ensemble approach it is assumed that snapshots are completely decorrelated
		self.tau=tau    # Artificial decay length applied to correlation funcs

		self.second_order_divergence=0.0 # compute divergence term of 2nd order cumulant

		# funtions needed to compute the cumulant response
		self.corr_func_cl=np.zeros((1,1))
		self.spectral_dens=np.zeros((1,1))
		self.corr_func_3rd_cl=np.zeros((1,1))
		self.corr_func_3rd_qm_freq=np.zeros((1,1))
		self.corr_func_3rd_qm=np.zeros((1,1))

		# Herzberg-Teller correlation functions
		self.corr_func_cross_cl=np.zeros((1,1)) # classical cross correlation function between
		self.corr_func_dipole_cl=np.zeros((1,1)) # energy gap and dipole moment, as well as pure
						         # dipole corr

		# HT lineshape functions
		self.A_HT2=np.zeros((1,1),dtype=complex)
		self.A_HT3=np.zeros((1,1),dtype=complex)

		# cumulant lineshape functions
		self.g2=np.zeros((1,1))
		self.g3=np.zeros((1,1))

		# 2DES 3rd order cumulant lineshape functions
		self.h1=np.zeros((1,1,1),dtype=complex)
		self.h2=np.zeros((1,1,1),dtype=complex)
		self.h4=np.zeros((1,1,1),dtype=complex)
		self.h5=np.zeros((1,1,1),dtype=complex)
	
		# response functions
		self.ensemble_response=np.zeros((1,1))
		self.cumulant_response=np.zeros((1,1))


	# currently only works for 2nd order
	def calc_ht_correction(self,temp,max_t,num_steps):
		kbT=temp*const.kb_in_Ha
		sampling_rate=1.0/self.time_step*math.pi*2.0
		# now construct correlation functions
		self.corr_func_dipole_cl=ht.construct_corr_func_dipole(self.dipole_fluct,self.num_trajs,self.tau,self.time_step)
		self.corr_func_cross_cl=ht.construct_corr_func_cross(self.dipole_fluct,self.fluct,self.num_trajs,self.tau,self.time_step)
		# Compute spectral density: this is really only done for analysis purposes:
		sd=cumulant.compute_spectral_dens(self.corr_func_dipole_cl,kbT, sampling_rate,self.time_step)
		np.savetxt('Dipole_dipole_spectral_density.dat',sd)
		sd=cumulant.compute_spectral_dens(self.corr_func_cross_cl,kbT, sampling_rate,self.time_step)
                np.savetxt('Dipole_energy_cross_spectral_density.dat',sd)

		# now compute dipole reorganization and the renormalized dipole moment
		self.dipole_reorg=ht.compute_dipole_reorg(self.corr_func_cross_cl, kbT,sampling_rate, self.time_step)
		self.dipole_renorm=np.sqrt(self.dipole_mom_av**2.0-2.0*self.dipole_mom_av*self.dipole_reorg+self.dipole_reorg**2.0)

		# now construct correlation functions in the frequency domain:
		corr_func_cross_freq=ht.compute_corr_func_freq(self.corr_func_cross_cl,sampling_rate,self.time_step)
		corr_func_dipole_freq=ht.compute_corr_func_freq(self.corr_func_dipole_cl,sampling_rate,self.time_step)
		# now evaluate 2nd order cumulant correction term. 
		self.A_HT2=ht.compute_HT_term_2nd_order(corr_func_dipole_freq,corr_func_cross_freq,self.dipole_mom_av,self.dipole_renorm,self.dipole_reorg,kbT,max_t,num_steps)

	def calc_2nd_order_divergence(self):
		omega_step=self.spectral_dens[1,0]-self.spectral_dens[0,0]
		self.second_order_divergence=cumulant.calc_2nd_order_cumulant_divergence(self.corr_func_cl,omega_step,self.time_step)

	def calc_2nd_order_corr(self):
		self.corr_func_cl=cumulant.construct_corr_func(self.fluct,self.num_trajs,self.tau,self.time_step)

	def calc_3rd_order_corr(self,corr_length,stdout):
		self.corr_func_3rd_cl=cumulant.construct_corr_func_3rd(self.fluct,self.num_trajs,corr_length,self.tau,self.time_step,stdout)
                # HACK: PRINT correlation function
		twoDES.print_2D_spectrum('classical_third_order_corr.dat',self.corr_func_3rd_cl,False)

	def calc_spectral_dens(self,temp):
		kbT=temp*const.kb_in_Ha
		sampling_rate=1.0/self.time_step*math.pi*2.0   # angular frequency associated with the sampling time step
		self.spectral_dens=cumulant.compute_spectral_dens(self.corr_func_cl,kbT, sampling_rate,self.time_step)

	def calc_g2(self,temp,max_t,num_steps,stdout):
		kbT=temp*const.kb_in_Ha
		self.g2=cumulant.compute_2nd_order_cumulant_from_spectral_dens(self.spectral_dens,kbT,max_t,num_steps,stdout)

	def calc_corr_func_3rd_qm_freq(self,temp,low_freq_filter):
		kbT=temp*const.kb_in_Ha
		sampling_rate_in_fs=1.0/(self.time_step*const.fs_to_Ha)
		self.corr_func_3rd_qm_freq=cumulant.construct_corr_func_3rd_qm_freq(self.corr_func_3rd_cl,kbT,sampling_rate_in_fs,low_freq_filter)
	
	def calc_corr_func_3rd_qm(self,temp,low_freq_filter):
		kbT=temp*const.kb_in_Ha
		sampling_rate_in_fs=1.0/(self.time_step*const.fs_to_Ha)
		self.corr_func_3rd_qm=cumulant.construct_corr_func_3rd_qm(self.corr_func_3rd_cl,kbT,sampling_rate_in_fs,low_freq_filter)


	def calc_g3(self,temp,max_t,num_steps,low_freq_filter,stdout):
		kbT=temp*const.kb_in_Ha
		sampling_rate_in_fs=1.0/(self.time_step*const.fs_to_Ha)
		self.g3=cumulant.compute_lineshape_func_3rd(self.corr_func_3rd_cl,kbT,sampling_rate_in_fs,max_t,num_steps,low_freq_filter,stdout)

	def calc_h1(self,max_t,num_steps):
		self.h1=cumulant.compute_h1_func(self.corr_func_3rd_qm_freq,max_t,num_steps)

	def calc_h2(self,max_t,num_steps):
		self.h2=cumulant.compute_h2_func(self.corr_func_3rd_qm_freq,max_t,num_steps)

	def calc_h4(self,max_t,num_steps):
		self.h4=cumulant.compute_h4_func(self.corr_func_3rd_qm_freq,max_t,num_steps)

	def calc_h5(self,max_t,num_steps):
		self.h5=cumulant.compute_h5_func(self.corr_func_3rd_qm_freq,max_t,num_steps)

	def calc_cumulant_response(self,is_3rd_order,is_emission,is_ht):
		self.cumulant_response=construct_full_cumulant_response(self.g2,self.g3,self.mean,is_3rd_order,is_emission)	
		if is_ht: # add herzberg-teller correction
			for i in range(self.cumulant_response.shape[0]):
				self.cumulant_response[i,1]=self.cumulant_response[i,1]*self.A_HT2[i,1]

	def calc_ensemble_response(self,max_t,num_steps):
		# Adjust for the fact that ensemble spectrum already contains dipole moment scaling
		self.ensemble_response=1.0/(self.dipole_mom_av**2.0)*construct_full_ensemble_response(self.fluct,self.dipole_mom, self.mean, max_t,num_steps,self.tau)

