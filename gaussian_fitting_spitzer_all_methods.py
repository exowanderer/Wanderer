from numpy      import indices, nanmedian, nanmean, nanstd, where, isnan, bitwise_and, ones, dtype, array, ravel, int32, zeros, exp, empty, random, arange, inf, sqrt, shape
from scipy      import optimize
from functools  import partial
from lmfit      import Model, Parameters

uniform = random.uniform
normal  = random.normal

try:
    from skimage.filters import gaussian as gaussianFilter
    print('Sci-kit Image Gaussian Filter Exists')
except:    
    gaussianFilter = lambda x,y:x
    print('Sci-kit Image Gaussian Filter Does Not Exists; Gaussian smoothing will not do anything')

try:
    from multiprocessing import Pool, cpu_count
    mp_exists = True
    print('Package multiprocessing Exists')
except:
    mp_exists = False
    print('Package multiprocessing Does Not Exists; every will be about 3 times slower')

def moments(data):
    """Returns (height, x, y, width_x, width_y,offset)
    the gaussian parameters of a 2D distribution by calculating its
    moments """
    total = data.sum()
    X, Y = indices(data.shape)
    x = (X*data).sum()/total
    y = (Y*data).sum()/total
    height = data.max()
    firstq = nanmedian(data[data < nanmedian(data)])
    thirdq = nanmedian(data[data > nanmedian(data)])
    offset = nanmedian(data[where(bitwise_and(data > firstq,
                                                    data < thirdq))])
    places = where((data-offset) > 4*nanstd(data[where(bitwise_and(
                                      data > firstq, data < thirdq))]))
    width_y = nanstd(places[0])
    width_x = nanstd(places[1])
    # These if statements take into account there might only be one significant
    # point above the background when that is the case it is assumend the width
    # of the gaussian must be smaller than one pixel
    if width_y == 0.0:
        width_y = 0.5
    if width_x == 0.0:
        width_x = 0.5

    height -= offset
    return height, y, x, width_y, width_x, offset

def gaussian(height, center_y, center_x, width_y, width_x, offset, yy, xx):
    """Returns a gaussian function with the given parameters"""
    width_x = float(width_x)
    width_y = float(width_y)
    
    chiY    = (center_y - yy) / width_y
    chiX    = (center_x - xx) / width_x
    
    return height * exp(-0.5*(chiY**2 + chiX**2)) + offset

def fitgaussian(data, init_params=None, weights=False):
    """Returns (height, y, x, width_y, width_x)
    the gaussian parameters of a 2D distribution found by a fit
    Weights must be the same size as the data, but every point
    contains the value of the weight of the pixel"""
    
    if isinstance(weights, type(False)):
        weights = ones(data.shape, dtype=float)
    elif weights.dtype != dtype('float'):
        weights = array(weights, dtype=float)
    
    params  = moments(data) if init_params is None else init_params
    yy,xx   = indices(data.shape)
    gs2D    = partial(gaussian, yy=yy,xx=xx)
    
    errorfunction = lambda p: ravel((gs2D(*p) - data)*weights)
    
    p, success = optimize.leastsq(errorfunction, params)
    
    return p

def fit_one_center(image, ylower, yupper, xlower, xupper, init_params, nSig=False, method='gauss', bSize = 7):
    
    subFrameNow = image[ylower:yupper, xlower:xupper]
    subFrameNow[isnan(subFrameNow)] = nanmedian(subFrameNow)
    
    subFrameNow = gaussianFilter(subFrameNow, nSig) if not isinstance(nSig, bool) else subFrameNow
    
    return fitgaussian(subFrameNow, init_params)

def lame_lmfit_gaussian_centering(imageCube, yguess=15, xguess=15, subArraySize=10, init_params=None, nSig=False, useMoments=False, method='leastsq'):
    imageSize  = imageCube.shape[1]
    
    nparams    = 6
    if init_params is None:
        useMoments = True
        init_params = moments(imageCube[0])
    
    ihg, iyc, ixc, iyw, ixw, ibg  = arange(nparams)
    lmfit_init_params = Parameters()
    lmfit_init_params.add_many(
        ('height'  , init_params[ihg], True  , 0.0 , inf   ),
        ('center_y', init_params[iyc], True  , 0.0 , imageSize),
        ('center_x', init_params[ixc], True  , 0.0 , imageSize),
        ('width_y' , init_params[iyw], True  , 0.0 , imageSize),
        ('width_x' , init_params[ixw], True  , 0.0 , imageSize),
        ('offset'  , init_params[ibg], True))
    
    gfit_model = Model(gaussian, independent_vars=['yy', 'xx'])
    
    yy0, xx0 = indices(imageCube[0].shape)
    
    npix   = subArraySize//2
    ylower = yguess - npix
    yupper = yguess + npix
    xlower = xguess - npix
    xupper = xguess + npix
    
    ylower, xlower, yupper, xupper = int32([ylower, xlower, yupper, xupper])
    
    yy = yy0[ylower:yupper, xlower:xupper]
    xx = xx0[ylower:yupper, xlower:xupper]
    
    heights, ycenters, xcenters, ywidths, xwidths, offsets = zeros((nparams, nFrames))
    
    for k, image in enumerate(imageCube):
        subFrameNow = image[ylower:yupper, xlower:xupper]
        subFrameNow[isnan(subFrameNow)] = nanmedian(subFrameNow)
        
        subFrameNow = gaussianFilter(subFrameNow, nSig) if not isinstance(nSig, bool) else subFrameNow
        
        init_params = moments(subFrameNow) if useMoments else init_params
        
        gfit_res    = gfit_model.fit(subFrameNow, params=lmfit_init_params, xx=xx, yy=yy, method=method)
        
        heights[k]  = gfit_res.best_values['height']
        ycenters[k] = gfit_res.best_values['center_y']
        xcenters[k] = gfit_res.best_values['center_x']
        ywidths[k]  = gfit_res.best_values['width_y']
        xwidths[k]  = gfit_res.best_values['width_x']
        offsets[k]  = gfit_res.best_values['offset']
    
    return heights, ycenters, xcenters, ywidths, xwidths, offsets

def lmfit_one_center(image, yy, xx, gfit_model, lmfit_init_params, yupper, ylower, xupper, xlower, useMoments=True, nSig=False, method='leastsq'):
    
    subFrameNow = image[ylower:yupper, xlower:xupper]
    subFrameNow[isnan(subFrameNow)] = nanmedian(subFrameNow)
    
    subFrameNow = gaussianFilter(subFrameNow, nSig) if not isinstance(nSig, bool) else subFrameNow
    
    init_params = moments(subFrameNow) if useMoments else list(lmfit_init_params.valuesdict().values())
    
    nparams     = 6
    ihg, iyc, ixc, iyw, ixw, ibg  = arange(nparams)
    
    lmfit_init_params.height   = init_params[ihg]
    lmfit_init_params.center_y = init_params[iyc]
    lmfit_init_params.center_x = init_params[ixc]
    lmfit_init_params.widths_y = init_params[iyw]
    lmfit_init_params.widths_x = init_params[ixw]
    lmfit_init_params.offset   = init_params[ibg]
    
    gfit_res    = gfit_model.fit(subFrameNow, params=lmfit_init_params, xx=xx, yy=yy, method=method)
    
    return gfit_res.best_values

def mp_lmfit_gaussian_centering(imageCube, yguess=15, xguess=15, subArraySize=10, init_params=None, useMoments=False, nCores=cpu_count(), nSig=False, method='leastsq'):
    imageSize  = imageCube.shape[1]
    
    nparams    = 6
    if init_params is None:
        useMoments = True
        init_params = moments(imageCube[0])
    
    ihg, iyc, ixc, iyw, ixw, ibg  = arange(nparams)
    lmfit_init_params = Parameters()
    lmfit_init_params.add_many(
        ('height'  , init_params[ihg], True  , 0.0 , inf   ),
        ('center_y', init_params[iyc], True  , 0.0 , imageSize),
        ('center_x', init_params[ixc], True  , 0.0 , imageSize),
        ('width_y' , init_params[iyw], True  , 0.0 , imageSize),
        ('width_x' , init_params[ixw], True  , 0.0 , imageSize),
        ('offset'  , init_params[ibg], True))
    
    gfit_model = Model(gaussian, independent_vars=['yy', 'xx'])
    
    yy0, xx0 = indices(imageCube[0].shape)
    
    npix   = subArraySize//2
    ylower = yguess - npix
    yupper = yguess + npix
    xlower = xguess - npix
    xupper = xguess + npix
    
    ylower, xlower, yupper, xupper = int32([ylower, xlower, yupper, xupper])
    
    yy = yy0[ylower:yupper, xlower:xupper]
    xx = xx0[ylower:yupper, xlower:xupper]
    
    pool = Pool(nCores)
    
    func = partial(lmfit_one_center, yy=yy, xx=xx, gfit_model=gfit_model, lmfit_init_params=lmfit_init_params, 
                                        yupper=yupper, ylower=ylower, xupper=xupper, xlower=xlower, method=method)
    
    gparams = pool.starmap(func, zip(imageCube))
    
    pool.close()
    pool.join()
    
    heights, ycenters, xcenters, ywidths, xwidths, offsets = zeros((nparams, nFrames))
    for k, gp in enumerate(gparams):    
        heights[k]  = gp['height']
        ycenters[k] = gp['center_y']
        xcenters[k] = gp['center_x']
        ywidths[k]  = gp['width_y']
        xwidths[k]  = gp['width_x']
        offsets[k]  = gp['offset']
    
    return heights, ycenters, xcenters, ywidths, xwidths, offsets

def mp_scipy_gaussian_centering(imageCube, init_params=None, yguess=15, xguess=15, subArraySize=10, nSig=False, nCores=cpu_count()):
    '''
        This is the main Gaussian centering function. Call this with the defaults will use multiprocessing.
        
        Parameters:
        
            imageCube (3D-array): an array of images with shape (nFrames, 32, 32)
            yguess         (int): the initial guess for the y-position to slice the subFrame
            xguess         (int): the initial guess for the x-position to slice the subFrame
            SubArraySize   (int): the size of the (soon-to-be) square subarray
            nSig         (float): the width of the Gaussian kernel to be used with Gaussian smooth (not-recommended)
            nCores         (int): an integer value of cores to be used if multiprocessing is enables -- assumed to be the max number of cores, because "why not?"
        
        Returns:
            centering_GaussianFit  (2D-array): a 2D array of (y,x) center values, with shape (nFrames,2)
            widths_GaussianFit     (2D-array): a 2D array of (y,x) width values, with shape (nFrames,2)
            heights_GaussianFit    (1D-array): a 1D array of height values, with shape (nFrames,)
            background_GaussianFit (1D-array): a 1D array of offset values, with shape (nFrames,) (offset ~ background)
        
        Usage:
            >>> imageCube = stack_of_spitzer_images_from_memory
            >>> centering_GaussianFit, widths_GaussianFit, heights_GaussianFit, background_GaussianFit = mp_scipy_gaussian_centering(imageCube)
    '''
    
    y,x = 0,1
            
    npix    = subArraySize//2
    nframes = imageCube.shape[0]
    
    yy, xx = indices(imageCube[0].shape)
    
    ylower = yguess - npix
    yupper = yguess + npix
    xlower = xguess - npix
    xupper = xguess + npix
    
    ylower, xlower, yupper, xupper = int32([ylower, xlower, yupper, xupper])
    
    yinds = yy[ylower:yupper, xlower:xupper]
    xinds = xx[ylower:yupper, xlower:xupper]
    
    heights   = zeros(nframes)
    ycenters  = zeros(nframes)
    xcenters  = zeros(nframes)
    ywidths   = zeros(nframes)
    xwidths   = zeros(nframes)
    offsets   = zeros(nframes)
    
    # Gaussian fit centering
    # This is like a for-loop
    pool = Pool(nCores) # This starts the multiprocessing call to arms
    
    func = partial(fit_one_center, init_params=init_params, nSig=nSig, method='gauss', ylower=ylower, yupper=yupper, xlower=xlower, xupper=xupper)
    
    gaussian_centers = pool.starmap(func, zip(imageCube)) # the order is very important
    
    pool.close()
    pool.join()
    
    nparams = 6
    ihg, iyc, ixc, iyw, ixw, ibg = arange(nparams)
    
    #print('Finished with Fitting Centers. Now assigning to instance values.')
    for kframe, gaussP in enumerate(gaussian_centers):
        ycenters[kframe]  = gaussP[iyc] + ylower
        xcenters[kframe]  = gaussP[ixc] + xlower
        ywidths[kframe]   = gaussP[iyw]
        xwidths[kframe]   = gaussP[ixw]
        
        heights[kframe]   = gaussP[ihg]
        offsets[kframe]   = gaussP[ibg]
    
    return heights, ycenters, xcenters, ywidths, xwidths, offsets

def lame_scipy_gaussian_centering(imageCube, init_params=None, yguess=15, xguess=15, subArraySize=10, nSig=False):
    '''
        This is the lame version of Gaussian centering function. Call this with the defaults will use *NOT* multiprocessing.        
        
        Parameters:
        
            imageCube (3D-array): an array of images with shape (nFrames, 32, 32)
            yguess         (int): the initial guess for the y-position to slice the subFrame
            xguess         (int): the initial guess for the x-position to slice the subFrame
            SubArraySize   (int): the size of the (soon-to-be) square subarray
            nSig         (float): the width of the Gaussian kernel to be used with Gaussian smooth (not-recommended)
        
        Returns:
            centering_GaussianFit  (2D-array): a 2D array of (y,x) center values, with shape (nFrames,2)
            widths_GaussianFit     (2D-array): a 2D array of (y,x) width values, with shape (nFrames,2)
            heights_GaussianFit    (1D-array): a 1D array of height values, with shape (nFrames,)
            background_GaussianFit (1D-array): a 1D array of offset values, with shape (nFrames,) (offset ~ background)
        
        Usage:
            >>> imageCube = stack_of_spitzer_images_from_memory
            >>> centering_GaussianFit, widths_GaussianFit, heights_GaussianFit, background_GaussianFit = lame_scipy_gaussian_centering(imageCube)
    '''
    
    y,x = 0,1
    
    npix    = subArraySize//2
    nframes = imageCube.shape[0]
    
    yy, xx = indices(imageCube[0].shape)
    
    ylower = yguess - npix
    yupper = yguess + npix
    xlower = xguess - npix
    xupper = xguess + npix
    
    ylower, xlower, yupper, xupper = int32([ylower, xlower, yupper, xupper])
    
    yinds = yy[ylower:yupper, xlower:xupper]
    xinds = xx[ylower:yupper, xlower:xupper]
    
    heights   = zeros(nframes)
    ycenters  = zeros(nframes)
    xcenters  = zeros(nframes)
    ywidths   = zeros(nframes)
    xwidths   = zeros(nframes)
    offsets   = zeros(nframes)
    
    # Gaussian fit centering
    # This is like a for-loop
    
    func = partial(fit_one_center, init_params=init_params, nSig=nSig, method='gauss', ylower=ylower, yupper=yupper, xlower=xlower, xupper=xupper)
    
    gaussP = []
    for k, image in enumerate(imageCube):
        gaussP.append(func(image))
    
    nparams = 6
    ih, iyc, ixc, iyw, ixw, io = arange(nparams)
    
    print('Finished with Fitting Centers. Now assigning to instance values.')
    for kframe, gaussP in enumerate(gaussP):
        ycenters[kframe]  = gaussP[iyc] + ylower
        xcenters[kframe]  = gaussP[ixc] + xlower
        ywidths[kframe]   = gaussP[iyw]
        xwidths[kframe]   = gaussP[ixw]
        
        heights[kframe]   = gaussP[ih]
        offsets[kframe]   = gaussP[io]
    
    return heights, ycenters, xcenters, ywidths, xwidths, offsets

def compute_flux_weighted_centroid(imageCube, yxguess, skybg, subSize=5):
    '''
        Flux-weighted centroiding (Knutson et al. 2008)
        xpos and ypos are the rounded pixel positions of the star
    '''
    
    y,x = 0,1
    
    ypos,xpos= yxguess
    ## extract a box around the star:
    
    ylower   = int(ypos-subSize)
    yupper   = int(ypos+subSize+1)
    xlower   = int(xpos-subSize)
    xupper   = int(xpos+subSize+1)
    
    nFrames  = imageCube.shape[0]
    
    flux_weighted_centroids = zeros((nFrames, 2))
    
    yrng  = arange(2*subSize+1)
    xrng  = arange(2*subSize+1)
    
    print('Computing Flux Weighted Centroids')
    for kf in range(nFrames):
        subImage = imageCube[kf][ylower:yupper, xlower:xupper].copy()#.transpose()
        
        ## add up the flux along x and y
        yflux = (subImage - skybg[kf]).sum(axis=y)
        xflux = (subImage - skybg[kf]).sum(axis=x)
        
        ## get the flux weighted average position:
        ypeak = sum(yflux * yrng) / sum(yflux) + (ypos - float(subSize))
        xpeak = sum(xflux * xrng) / sum(xflux) + (xpos - float(subSize))
        
        flux_weighted_centroids[kf] = ypeak, xpeak
    shape(flux_weighted_centroids)
    return flux_weighted_centroids.T[::-1]

def generate_spitzer_tso_simple(nFrames, imageSize=32, y_scatter=0.1, x_scatter=0.05, fwhm=1.5, height=3e4, noisy=True):
    
    # set up size of data cube
    imageCube = empty((nFrames, imageSize, imageSize))
    
    ycenters  = normal(imageSize//2-1,y_scatter, nFrames)
    xcenters  = normal(imageSize//2-1,x_scatter, nFrames)
    
    ywidths   = normal(fwhm, 1e-2*fwhm, nFrames)
    xwidths   = normal(fwhm, 1e-2*fwhm, nFrames)
    
    heights   = normal(height, 1e-2*height, nFrames)
    offsets   = 0*normal(1e-4*height, 1e-6*height, nFrames)
    
    yy, xx = indices((imageSize,imageSize))
    
    for kf, (yc, xc, ys, xs, hg, bg) in enumerate(zip(ycenters, xcenters, ywidths, xwidths, heights, offsets)):
        imageCube[kf] = gaussian(hg, yc, xc, ys, xs, bg, yy, xx)
        imageCube[kf] = normal(imageCube[kf], sqrt(imageCube[kf])) if noisy else imageCube[kf] # add Poisson noise
    
    return imageCube, heights, ycenters, xcenters, ywidths, xwidths, offsets

if mp_exists:
    scipy_gaussian_centering = mp_lmfit_gaussian_centering
else:
    scipy_gaussian_centering = lame_lmfit_gaussian_centering

if __name__ == '__main__':
    from pylab import imshow, plot, show
    from sys   import argv
    from time  import time
    
    plotRaw = False # Plot the raw values for both input and output values
    plotRel = True  # Plot the relative differnece between input and output values
    
    nFrames = int(argv[1]) if len(argv) > 1 else 1000
    
    init_params = [3e4, 15., 15., 1.5, 1.5, 0.0]
    
    imageCube, input_heights, input_ycenters, input_xcenters, input_ywidths, input_xwidths, input_offsets = generate_spitzer_tso_simple(nFrames, y_scatter=.1, x_scatter=.1)
    
    if plotRaw:
        plot(input_xcenters , input_ycenters,'.')
    
    start = time()
    gauss_heights, gauss_ycenters, gauss_xcenters, gauss_ywidths, gauss_xwidths, gauss_offsets = lame_scipy_gaussian_centering(imageCube)
    end   = time() - start
    print('Lame Scipy took {} seconds at {} iterations per seconds'.format(end, nFrames / end))
    
    start = time()
    gauss_heights, gauss_ycenters, gauss_xcenters, gauss_ywidths, gauss_xwidths, gauss_offsets = mp_scipy_gaussian_centering(imageCube)
    end   = time() - start
    print('MP Scipy took {} seconds at {} iterations per seconds'.format(end, nFrames / end))
    
    if plotRaw:
        plot(gauss_ycenters, gauss_xcenters,'.')
    if plotRel:
        plot((input_xcenters- gauss_xcenters) / input_xcenters, (input_ycenters- gauss_ycenters)/input_ycenters,'.')
    
    Y_diff = (input_ycenters- gauss_ycenters) / input_ycenters
    X_diff = (input_xcenters- gauss_xcenters) / input_xcenters
    
    print('Scipy Y_Mean={} Y_Std={} X_Mean={} X_Std={}'.format(nanmean(Y_diff), nanstd(Y_diff), nanmean(X_diff), nanstd(X_diff)))
    
    start = time()
    gauss_heights, gauss_ycenters, gauss_xcenters, gauss_ywidths, gauss_xwidths, gauss_offsets = lame_lmfit_gaussian_centering(imageCube, method='leastsq')
    end   = time() - start
    print('Lame LMFIT took {} seconds at {} iterations per seconds'.format(end, nFrames / end))
    
    start = time()
    gauss_heights, gauss_ycenters, gauss_xcenters, gauss_ywidths, gauss_xwidths, gauss_offsets = mp_lmfit_gaussian_centering(imageCube, method='leastsq')
    end   = time() - start
    print('MP LMFIT took {} seconds at {} iterations per seconds'.format(end, nFrames / end))
    
    Y_diff = (input_ycenters- gauss_ycenters) / input_ycenters
    X_diff = (input_xcenters- gauss_xcenters) / input_xcenters
    
    print('LMFIT Y_Mean={} Y_Std={} X_Mean={} X_Std={}'.format(nanmean(Y_diff), nanstd(Y_diff), nanmean(X_diff), nanstd(X_diff)))
    
    fwc_ycenters, fwc_xcenters = compute_flux_weighted_centroid(imageCube, [15.,15.], skybg=nanmedian(imageCube, axis=(1,2)))
    
    if plotRaw:
        plot(gauss_ycenters, gauss_xcenters,'.')
        plot(fwc_xcenters, fwc_ycenters,'.')
    if plotRel:
        plot((input_xcenters- gauss_xcenters) / input_xcenters, (input_ycenters- gauss_ycenters)/input_ycenters,'.')
        plot((input_xcenters- fwc_xcenters) / input_xcenters, (input_ycenters- fwc_ycenters)/input_ycenters,'.')
        plot((gauss_xcenters- fwc_xcenters) / gauss_xcenters, (gauss_ycenters- fwc_ycenters)/gauss_ycenters,'.')
    
    if plotRaw or plotRel:
        show()