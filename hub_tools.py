"""
This script simulates the centre of a Hub-Filament System with saturated pixels
"""

### imports
import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import curve_fit
from astropy.io import fits

def gaussian(points,mx,my,N,theta,FWHMx,FWHMy):
	"""
	Gaussian function in 2D:
		- points = (x,y) is the grid array at which the function is being evaluated
		- (mx,my) = (mu_x,mu_y) is the centre of the distribution
		- N is an arbitrary normalization constant
		- FWHM is given in the same units as the 'points' argument
	"""
	sigmax = FWHMx/(2*np.sqrt(2*np.log(2)))
	sigmay = FWHMy/(2*np.sqrt(2*np.log(2)))
	alphax = 1/(2*sigmax**2)
	alphay = 1/(2*sigmay**2)
	x,y = points
	xl = x*np.cos(theta) - y*np.sin(theta)
	yl = x*np.sin(theta) + y*np.cos(theta)
	mxl = mx*np.cos(theta) - my*np.sin(theta)
	myl = mx*np.sin(theta) + my*np.cos(theta)
	z = N * np.exp( - alphax*(xl-mxl)**2 - alphay*(yl-myl)**2 )
	return z

def gaussianMult(points,*args):
	""" Sum multiple 2D gaussian functions. """
	z = 0
	for i in range(len(args)//6):
		mx,my,N,theta,FWHMx,FWHMy = args[6*i:6*(i+1)]
		z += gaussian(points,mx,my,N,theta,FWHMx,FWHMy)
	return z


def simulate(N):
	""" Simulate noisy data to fit """
	x = np.linspace(-10,10,N)
	y = x.copy()
	grid = np.meshgrid(x,y)
	image = gaussian(grid,-2,-1,1,0,18.2,18.2)
	image += gaussian(grid,1,2,1.5,0,18.2,18.2)
	image += gaussian(grid,1,-2,1,0,18.2,18.2)
	return grid,image

def fitter(grid,data,sat,mu=[],theta=[],FWHM=[],peaks=1,helper_peaks=False,var_pos=0.1,var_theta=0.1,var_FWHM=0.01):
	"""
	Function takes array image, its grid and boolean array of same shape,
	which is True where pixels are saturated and False elsewhere.
	Returns the image with saturated pixels corrected.
	Saturated pixels in data can be represented by both 'nan' and 0 (zero) values.
	"""

	Ny,Nx = data.shape # number of points in x and y axes
	X,Y = grid # index grid
    
    # initial guess for parameters
	if len(mu)==0:
		mu_x = X[sat].mean()
		mu_y = Y[sat].mean()
		mu = np.array(peaks*[[mu_x,mu_y]])
	N = data[np.isnan(data)==False].max()
	if len(theta)==0:
		theta = np.array(peaks*[np.pi])
	if len(FWHM)==0:
		FWHM = np.array(peaks*[[18.2,18.2]])/3600

	lower_bounds,upper_bounds = [],[]
	guess_params = np.empty(6*peaks)
	for i in range(peaks):
		mu_x,mu_y = mu[i,:]
		FWHMx,FWHMy = FWHM[i,:]
		guess_params[i*6:(i+1)*6] = [mu_x,mu_y,N*1.1,theta[i],FWHMx,FWHMy]
		
		lower_bounds += [
			X[sat].min() - var_pos,
			Y[sat].min() - var_pos,
			N,
			theta[i] - var_theta,
			FWHMx * (1 - var_FWHM),
			FWHMy * (1 - var_FWHM)]

		upper_bounds += [
			X[sat].max() + var_pos,
			Y[sat].max() + var_pos,
			np.inf,
			theta[i] + var_theta,
			FWHMx * (1 + var_FWHM),
			FWHMy * (1 + var_FWHM)]

	# add helper_peaks to the mix
	if helper_peaks:
		FWHMx,FWHMy = FWHM.mean(axis=0)

		data0 = data[1:-1,1:-1]
		prex = np.zeros(data.shape)
		posx = prex.copy()
		prey = prex.copy()
		posy = prex.copy()
		prex[1:-1,1:-1] = data0 - data[1:-1,:-2]
		posx[1:-1,1:-1] = data0 - data[1:-1,2:]
		prey[1:-1,1:-1] = data0 - data[:-2,1:-1]
		posy[1:-1,1:-1] = data0 - data[2:,1:-1]

		bool_maxima = (prex>0)&(posx>0)&(prey>0)&(posy>0)
		maxima = np.array([X[bool_maxima],Y[bool_maxima],data[bool_maxima]])
		m = len(maxima[0,:])

		helper_params = np.empty(m*6)
		for i in range(m):
			mu_x,mu_y,N = maxima[:,i]
			helper_params[i*6:(i+1)*6] = [mu_x,mu_y,N,0,FWHMx,FWHMy]

			lower_bounds += [
				mu_x - var_pos,
				mu_y - var_pos,
				N * 0.9,
				-np.pi,
				FWHMx * (1 - var_FWHM),
				FWHMy * (1 - var_FWHM)]

			upper_bounds += [
				mu_x + var_pos,
				mu_y + var_pos,
				N * 1.1,
				np.pi,
				FWHMx * (1 + var_FWHM),
				FWHMy * (1 + var_FWHM)]
		guess_params = np.concatenate((guess_params,helper_params))

	fit_x = np.array([X[sat==False],Y[sat==False]])
	fit_data = data[sat==False]

	params,cov = curve_fit(gaussianMult,fit_x,fit_data,guess_params,bounds=(lower_bounds,upper_bounds),maxfev=4000)
	image = gaussianMult((X,Y),*params)
	image[sat==False] = data[sat==False]
	return params,image

def display_fits(file,lims=[],return_vals=False):
	"""
	Display a 2D array image from a standard FITS file.
	This function assumes the coordinates to be the galactic system,
	where longitude increases from right to left
	and latitude increases from bottom to top,
	both in degrees.

	The lims argument is a list which, if given, must contain:
	1. Left limit (xl)
	2. Right limit (xr)
	3. Bottom limit (yb)
	4. Top limit (yt)
	of the window in this order.
	"""
    
	# Open and read
	hdulist = fits.open(file)
	hdu = hdulist[0]
	header = hdu.header
	data = hdu.data

	# Get axes right
	x = header['crval1'] + header['cdelt1'] * (np.arange(0,header['naxis1'],1) - header['crpix1'])
	y = header['crval2'] + header['cdelt2'] * (np.arange(0,header['naxis2'],1) - header['crpix2'])
	# If window limits are given
	if len(lims)==0:
		xl,xr,yb,yt = x.max(),x.min(),y.min(),y.max()
	else:
		xl,xr,yb,yt = lims
    
	xsub = x[(x<=xl)&(x>=xr)]
	ysub = y[(y>=yb)&(y<=yt)]
    
	data_sub = data[(y>=yb)&(y<=yt),:][:,(x<=xl)&(x>=xr)]

	plt.figure(figsize=(8,8))
	plt.imshow(np.log10(data_sub),origin='lower',extent=(xl,xr,yb,yt))
	plt.show()

	if return_vals:
		grid = np.meshgrid(xsub,ysub)
		sat_area = np.isnan(data_sub)
		return grid,data_sub,sat_area



if __name__ == '__main__':

	grid,data = simulate(50)
	x,y = grid[0][0,:],grid[1][:,0]
	sat = data>0.5*data.max()
	ticks = np.arange(0,100)
	labels = np.linspace(-1,1,100)
	plt.imshow(data)
	plt.show()
	plt.imshow(sat)
	plt.show()

	data2 = data.copy()
	data2[sat] = 0
	plt.imshow(data2)
	plt.show()

	params,fit_data = fit(grid,data,sat,FWHM=np.array(3*[2*[18.2]]),peaks=3)

	plt.imshow(fit_data)
	plt.colorbar()
	plt.show()

	plt.imshow(fit_data-data)
	plt.colorbar()
	plt.show()

	print(params[:6])
	print(params[6:12])
	print(params[12:])