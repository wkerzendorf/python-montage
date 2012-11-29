import os
import glob
import shutil as sh
import warnings
import tempfile
pyfits_available = False
import commands as m
from status import MontageError


def _finalize(cleanup, work_dir, silence=False):
    if cleanup:
        # Deleting work directory
        if not silence: print "Deleting work directory %s" % work_dir
        sh.rmtree(work_dir)
    else:
        # Leave work directory as it is
        if not silence: print "Leaving work directory %s" % work_dir


try:
    try:
        import pyfits
        pyfits_available = True
    except ImportError:
        pass

    try:
        from astropy.io import fits as pyfits
        pyfits_available = True
    except ImportError:
        pass

    if not pyfits_available: raise ImportError('Neither pyfits nor astropy are available - either one of them is needed')


    def reproject_hdu(in_hdu, **kwargs):
        '''
        Reproject an image (HDU version)

        Required Arguments

            *in_hdu* [ pyfits HDU ]
                Input FITS file to be reprojected.

        Optional Arguments

            See reproject(...)
        '''

        # Make work directory
        work_dir = tempfile.mkdtemp() + '/'

        in_image = work_dir + '/in.fits'
        out_image = work_dir + '/out.fits'

        pyfits.writeto(in_image, in_hdu.data, in_hdu.header)

        reproject(in_image, out_image, **kwargs)

        out_hdu = pyfits.open(out_image)[0]

        return out_hdu

except:
    pass

try:

    import numpy

    def reproject_cube(in_image, out_image, header=None, bitpix=None,
        north_aligned=False, system=None, equinox=None, factor=None, common=False,
        cleanup=True, clobber=False, silent_cleanup=True):
        '''
        Cube reprojection routine.

        If one input/output image is specified, and the header argument is set,
        the routine is equivalent to using mProject or mProjectPP. If header= is
        not set, a new header is computed by taking into account the
        north_aligned, system, and equinox arguments (if set).

        Required Arguments

            *in_image* [ string ]
                Path of input FITS file to be reprojected.

            *out_image* [ string ]
                Path of output FITS file to be created.

        Optional Arguments

            *header* [ string ]
                Path to the header file to use for re-projection.

            *bitpix* [ value ]
                BITPIX value for the ouput FITS file (default is -64). Possible
                values are: 8 (character or unsigned binary integer), 16 (16-bit
                integer), 32 (32-bit integer), -32 (single precision floating
                point), -64 (double precision floating point).

            *north_aligned* [ True | False ]
                Align the pixel y-axis with North

            *system* [ value ]
                Specifies the coordinate system
                Possible values are: EQUJ EQUB ECLJ ECLB GAL SGAL

            *equinox* [ value ]
                If a coordinate system is specified, the equinox can also be given
                in the form YYYY. Default is J2000.

            *factor* [ value ]
                Drizzle factor (see mProject)

            *clobber* [ True | False ]  (default False)
                Overwrite the data cube if it already exists?

            *silent_cleanup* [ True | False ]  (default True)
                Hide messages related to tmp directory removal (there will be one
                for each plane of the cube if set to False)

        '''

        if header:
            if north_aligned or system or equinox:
                warnings.warn("header= is set, so north_aligned=, system=, and equinox= will be ignored")

        # Find path to input and output file
        in_image = os.path.abspath(in_image)
        out_image = os.path.abspath(out_image)

        if os.path.exists(out_image) and not clobber:
            raise IOError( "File '%s' already exists and clobber=False." % out_image )

        # Make work directory
        work_dir = tempfile.mkdtemp() + '/'

        # Set paths

        raw_dir = work_dir + 'raw/'
        final_dir = work_dir + 'final/'

        if header:
            header_hdr = os.path.abspath(header)
        else:
            header_hdr = work_dir + 'header.hdr'

        images_raw_tbl = work_dir + 'images_raw.tbl'
        images_tmp_tbl = work_dir + 'images_tmp.tbl'

        # Create raw directory
        os.mkdir(raw_dir)
        os.mkdir(final_dir)

        # Make new header
        if not header:
            m.mMakeHdr(images_raw_tbl, header_hdr, north_aligned=north_aligned,
                system=system, equinox=equinox)

        cubefile = pyfits.open(in_image)
        if len(cubefile[0].data.shape) != 3 or cubefile[0].header.get('NAXIS') != 3:
            raise Exception("Cube file must have 3 dimensions")

        # a temporary HDU that will be used to hold different data each time
        # and reproject each plane separately
        planefile = pyfits.PrimaryHDU(data=cubefile[0].data[0,:,:],
                header=cubefile[0].header)

        # generate a blank HDU to store the eventual projected cube

        # first must remove END card from .hdr file
        header_temp = header_hdr.replace(".hdr","_tmp.hdr")
        headerlines = open(header_hdr,'r').readlines()[:-1]
        w = open(header_temp,'w')
        w.writelines([line for line in headerlines])
        w.close()

        # when creating the new header, allow the 3rd axis to be
        # set by the input data cube
        newheader = pyfits.Header()
        newheader.fromTxtFile(header_temp)
        blank_data = numpy.zeros(
                [cubefile[0].header.get('NAXIS3'),
                newheader.get('NAXIS2'),
                newheader.get('NAXIS1')]
                )
        newcube = pyfits.PrimaryHDU(data=blank_data,header=newheader)

        for ii, plane in enumerate(cubefile[0].data):

            os.mkdir(final_dir + '%i' % ii)

            # reset the data plane within the temporary HDU
            planefile.data = plane

            # reproject the individual plane - exact size MUST be specified so that the
            # data can be put into the specified cube
            reprojected = reproject_hdu(planefile, header=header_hdr,
                    exact_size=True, factor=factor, bitpix=bitpix,
                    silent_cleanup=silent_cleanup)

            newcube.data[ii,:,:] = reprojected.data

        newcube.writeto(out_image,clobber=clobber)

        _finalize(cleanup, work_dir)

        return

except:
    pass


def mProject_auto(*args, **kwargs):
    '''
    Run mProject, automatically selecting whether to run mProject or
    mProjectPP if possible (fast plane-to-plane projection). For details on
    required and optional arguments, see help(mProject).
    '''
    try:
        m.mProjectPP(*args, **kwargs)
    except MontageError:
        m.mProject(*args, **kwargs)


def reproject(in_images, out_images, header=None, bitpix=None,
    north_aligned=False, system=None, equinox=None, factor=None, common=False,
    exact_size=False, hdu=None, cleanup=True, silent_cleanup=False):
    '''
    General-purpose reprojection routine.

    If one input/output image is specified, and the header argument is set,
    the routine is equivalent to using mProject or mProjectPP. If header= is
    not set, a new header is computed by taking into account the
    north_aligned, system, and equinox arguments (if set).

    If tuples of input/output images are specified, the tuples need to have
    the same number of elements. If header= is specified, all images are
    projected to this common projection. If header= is not specified, then a
    new header is computed a new header is computed by taking into account the
    north_aligned, system, and equinox arguments (if set). If common=False,
    then a header is computed for each individual image, whereas if
    common=True, an optimal header is computed for all images.

    Required Arguments

        *in_images* [ string | tuple or list of strings ]
            Path(s) of input FITS file(s) to be reprojected.

        *out_images* [ string | tuple or list of strings ]
            Path(s) of output FITS file(s) to be created.

    Optional Arguments

        *header* [ string ]
            Path to the header file to use for re-projection.

        *bitpix* [ value ]
            BITPIX value for the ouput FITS file (default is -64). Possible
            values are: 8 (character or unsigned binary integer), 16 (16-bit
            integer), 32 (32-bit integer), -32 (single precision floating
            point), -64 (double precision floating point).

        *north_aligned* [ True | False ]
            Align the pixel y-axis with North

        *system* [ value ]
            Specifies the coordinate system
            Possible values are: EQUJ EQUB ECLJ ECLB GAL SGAL

        *equinox* [ value ]
            If a coordinate system is specified, the equinox can also be given
            in the form YYYY. Default is J2000.

        *factor* [ value ]
            Drizzle factor (see mProject)

        *exact_size* [ True | False ]
            Whether to reproject the image(s) to the exact header specified
            (i.e. whether cropping is unacceptable).

        *hdu* [ value ]
            The HDU to use in the file(s)

        *silent_cleanup* [ True | False ]  (default False)
            Hide messages related to tmp directory removal

    Optional Arguments (multiple files only)

        *common* [ string ]
            Compute a common optimal header for all images (only used if
            header=None)
    '''

    if type(in_images) == str and type(out_images) == str:
        in_images = (in_images, )
        out_images = (out_images, )
    elif type(in_images) in [tuple, list] and type(out_images) in [tuple, list]:
        pass
    else:
        raise Exception("Inconsistent type for in_images (%s) and out_images (%s)" % (type(in_images), type(out_images)))

    if header:
        if north_aligned or system or equinox:
            warnings.warn("header= is set, so north_aligned=, system=, and equinox= will be ignored")

    if common and len(in_images) == 1:
        warnings.warn("only one image is being reprojected, so common= will be ignored")

    # Find path to input and output file
    in_images = [os.path.abspath(in_image) for in_image in in_images]
    out_images = [os.path.abspath(out_image) for out_image in out_images]

    if len(in_images) > 1 and not header and not common:
        for i, in_image in enumerate(in_images):
            reproject(in_images[i], out_images[i], bitpix=bitpix,
                north_aligned=north_aligned, system=system,
                equinox=equinox, factor=factor,
                exact_size=exact_size, cleanup=cleanup,
                silent_cleanup=silent_cleanup)
        return

    # Make work directory
    work_dir = tempfile.mkdtemp() + '/'

    # Set paths

    raw_dir = work_dir + 'raw/'
    final_dir = work_dir + 'final/'

    if header:
        header_hdr = os.path.abspath(header)
    else:
        header_hdr = work_dir + 'header.hdr'

    images_raw_tbl = work_dir + 'images_raw.tbl'
    images_tmp_tbl = work_dir + 'images_tmp.tbl'

    # Create raw directory
    os.mkdir(raw_dir)
    os.mkdir(final_dir)

    # Link to images
    for i, in_image in enumerate(in_images):
        os.mkdir(raw_dir + '%i' % i)
        os.symlink(in_image, raw_dir + '%i/image.fits' % i)

    # Make image table
    m.mImgtbl(raw_dir, images_raw_tbl, corners=True, recursive=True)

    # Make new header
    if not header:
        m.mMakeHdr(images_raw_tbl, header_hdr, north_aligned=north_aligned,
            system=system, equinox=equinox)

    for i, in_image in enumerate(in_images):

        os.mkdir(final_dir + '%i' % i)

        mProject_auto(in_images[i], final_dir + '%i/image_tmp.fits' % i,
                      header_hdr, hdu=hdu)

        if exact_size:
            m.mImgtbl(final_dir + '%i' % i, images_tmp_tbl, corners=True)
            m.mAdd(images_tmp_tbl, header_hdr,
                   final_dir + '%i/image.fits' % i,
                   img_dir=final_dir + '%i' % i, exact=True)
        else:
            os.symlink(final_dir + '%i/image_tmp.fits' % i,
                       final_dir + '%i/image.fits' % i)

        m.mConvert(final_dir + '%i/image.fits' % i, out_images[i],
                   bitpix=bitpix)

    _finalize(cleanup, work_dir, silence=silent_cleanup)

    return


def mosaic(input_dir, output_dir, header=None, mpi=False, n_proc=8,
           background_match=False, imglist=None, combine="mean",
           exact_size=False, cleanup=True, bitpix=-32, level_only=True,
           work_dir=None):

    if not combine in ['mean', 'median', 'count']:
        raise Exception("combine should be one of mean/median/count")

    # Check that there are files in the input directory
    if len(glob.glob('%s/*' % input_dir)) == 0:
        raise Exception("No files in input directory")

    # Find path to input and output directory
    input_dir = os.path.abspath(input_dir) + "/"
    output_dir = os.path.abspath(output_dir) + "/"

    # Make work directory
    if work_dir:
        work_dir = os.path.abspath(work_dir) + '/'
        if os.path.exists(work_dir):
            raise Exception("Work directory already exists")
        os.mkdir(work_dir)
    else:
        work_dir = tempfile.mkdtemp() + '/'

    images_raw_all_tbl = work_dir + 'images_raw_all.tbl'
    images_raw_tbl = work_dir + 'images_raw.tbl'
    images_projected_tbl = work_dir + 'images_projected.tbl'
    images_corrected_tbl = work_dir + 'images_corrected.tbl'
    corrections_tbl = work_dir + 'corrections.tbl'
    diffs_tbl = work_dir + 'diffs.tbl'
    stats_tbl = work_dir + 'stats.tbl'
    fits_tbl = work_dir + 'fits.tbl'

    raw_dir = work_dir + 'raw'
    projected_dir = work_dir + 'projected'
    corrected_dir = work_dir + 'corrected'
    diffs_dir = work_dir + 'diffs'

    header_hdr = work_dir + 'header.hdr'

    # Find path to header file if specified
    if header:
        header = os.path.abspath(header)

    # Find path to image list if specified
    if imglist:
        imglist = os.path.abspath(imglist)

    # Create output dir
    if os.path.exists(output_dir):
        raise Exception("Output directory already exists")
    else:
        os.mkdir(output_dir)

    # Create symbolic links
    os.symlink(input_dir, raw_dir)

    if header:
        os.symlink(header, header_hdr)

    # Create temporary directories for Montage
    os.mkdir(projected_dir)
    if background_match:
        os.mkdir(diffs_dir)
        os.mkdir(corrected_dir)

    # List frames to mosaic
    print "Listing raw frames"
    m.mImgtbl(raw_dir, images_raw_all_tbl, img_list=imglist, corners=True)

    # Compute header if needed
    if not header:
        print "Computing optimal header"
        m.mMakeHdr(images_raw_all_tbl, header_hdr)
        images_raw_tbl = images_raw_all_tbl
    else:
        print "Checking for coverage"
        m.mCoverageCheck(images_raw_all_tbl, images_raw_tbl, mode='header', header=header_hdr)

    # Projecting raw frames
    print "Projecting raw frames"
    m.mProjExec(images_raw_tbl, header_hdr, projected_dir, stats_tbl,
                raw_dir=raw_dir, mpi=mpi, n_proc=n_proc, exact=exact_size)

    # List projected frames
    m.mImgtbl(projected_dir, images_projected_tbl)

    if background_match:

        # Modeling background

        print "Modeling background"
        m.mOverlaps(images_projected_tbl, diffs_tbl)
        m.mDiffExec(diffs_tbl, header_hdr, diffs_dir, proj_dir=projected_dir,
                    mpi=mpi, n_proc=n_proc)
        m.mFitExec(diffs_tbl, fits_tbl, diffs_dir)
        m.mBgModel(images_projected_tbl, fits_tbl, corrections_tbl,
                   n_iter=32767, level_only=level_only)

        # Matching background
        print "Matching background"
        m.mBgExec(images_projected_tbl, corrections_tbl, corrected_dir,
                  proj_dir=projected_dir)
        sh.copy(corrections_tbl, output_dir)

        # Mosaicking frames
        print "Mosaicking frames"

        m.mImgtbl(corrected_dir, images_corrected_tbl)
        m.mAdd(images_corrected_tbl, header_hdr, output_dir + 'mosaic64.fits',
               img_dir=corrected_dir, type=combine, exact=exact_size)
        sh.copy(images_projected_tbl, output_dir)
        sh.copy(images_corrected_tbl, output_dir)

    else:

        # Mosaicking frames
        print "Mosaicking frames"

        m.mAdd(images_projected_tbl, header_hdr, output_dir + 'mosaic64.fits',
               img_dir=projected_dir, type=combine, exact=exact_size)
        sh.copy(images_projected_tbl, output_dir)

    m.mConvert(output_dir + 'mosaic64.fits', output_dir + 'mosaic.fits',
               bitpix=bitpix)
    m.mConvert(output_dir + 'mosaic64_area.fits',
               output_dir + 'mosaic_area.fits', bitpix=bitpix)

    os.remove(output_dir + "mosaic64.fits")
    os.remove(output_dir + "mosaic64_area.fits")

    _finalize(cleanup, work_dir)

    return
