def datacens_workflow_percent(SinkTag="func_preproc", wf_name="data_censoring"):

    """

        Modified version of CPAC.scrubbing.scrubbing +
                            CPAC.generate_motion_statistics.generate_motion_statistics +
                            CPAC.func_preproc.func_preproc

    `source: https://fcp-indi.github.io/docs/developer/_modules/CPAC/scrubbing/scrubbing.html`
    `source: https://fcp-indi.github.io/docs/developer/_modules/CPAC/generate_motion_statistics/generate_motion_statistics.html`
    `source: https://fcp-indi.github.io/docs/developer/_modules/CPAC/func_preproc/func_preproc.html`

    Description:
        Do the data censoring on the 4D functional data. First, it calculates the framewise displacement according to Power's method. Second, it
        indexes the volumes which FD is in the upper part in percent(determined by the threshold variable which is 5% by default). Thirdly, it excludes those volumes and one volume
        before and 2 volumes after the indexed volume. The workflow returns a 4D scrubbed functional data.

    Workflow inputs:
        :param func: The reoriented,motion occrected, nuissance removed and bandpass filtered functional file.
        :param FD: the frame wise displacement calculated by the MotionCorrecter.py script
        :param threshold: threshold of FD volumes which should be excluded
        :param SinkDir:
        :param SinkTag: The output directory in which the returned images (see workflow outputs) could be found in a subdirectory directory specific for this workflow..

    Workflow outputs:

        :return: datacens_workflow - workflow




    Balint Kincses
    kincses.balint@med.u-szeged.hu
    2018


    References
    ----------

    .. [1] Power, J. D., Barnes, K. A., Snyder, A. Z., Schlaggar, B. L., & Petersen, S. E. (2012). Spurious
           but systematic correlations in functional connectivity MRI networks arise from subject motion. NeuroImage, 59(3),
           2142-2154. doi:10.1016/j.neuroimage.2011.10.018

    .. [2] Power, J. D., Barnes, K. A., Snyder, A. Z., Schlaggar, B. L., & Petersen, S. E. (2012). Steps
           toward optimizing motion artifact removal in functional connectivity MRI; a reply to Carp.
           NeuroImage. doi:10.1016/j.neuroimage.2012.03.017

    .. [3] Jenkinson, M., Bannister, P., Brady, M., Smith, S., 2002. Improved optimization for the robust
           and accurate linear registration and motion correction of brain images. Neuroimage 17, 825-841.

    """


    import os
    import nipype
    import nipype.pipeline as pe
    import nipype.interfaces.utility as utility
    import nipype.interfaces.io as io
    import PUMI.utils.globals as globals
    import PUMI.utils.QC as qc

    SinkDir = os.path.abspath(globals._SinkDir_ + "/" + SinkTag)
    if not os.path.exists(SinkDir):
        os.makedirs(SinkDir)

    # Identitiy mapping for input variables
    inputspec = pe.Node(utility.IdentityInterface(fields=['func',
                                                          'FD',
                                                          'threshold']),
                        name='inputspec')
    inputspec.inputs.threshold = 5

    #TODO_ready check CPAC.generate_motion_statistics.generate_motion_statistics script. It may use the FD of Jenkinson to index volumes which violate the upper threhold limit, no matter what we set.
    # - we use the power method to calculate FD
    # Determine the indices of the upper part (which is defined by the threshold, deafult 5%) of values based on their FD values
    calc_upprperc = pe.MapNode(utility.Function(input_names=['in_file',
                                                        'threshold'],
                                           output_names=['frames_in_idx', 'frames_out_idx', 'percentFD', 'out_file', 'nvol'],
                                           function=calculate_upperpercent),
                               iterfield=['in_file'],
                             name='calculate_upperpercent')

    # Generate the weird input for the scrubbing procedure which is done in afni
    craft_scrub_input = pe.MapNode(utility.Function(input_names=['scrub_input', 'frames_in_1D_file'],
                                              output_names=['scrub_input_string'],
                                              function=get_indx),
                                   iterfield=['scrub_input', 'frames_in_1D_file'],
                                name='scrubbing_craft_input_string')
    # Scrub the image
    scrubbed_preprocessed = pe.MapNode(utility.Function(input_names=['scrub_input'],
                                                  output_names=['scrubbed_image'],
                                                  function=scrub_image),
                                       iterfield=['scrub_input'],
                                    name='scrubbed_preprocessed')

    myqc = qc.timecourse2png("timeseries", tag="040_censored")

    outputspec = pe.Node(utility.IdentityInterface(fields=['scrubbed_image', 'FD']),
                         name='outputspec')

    # save data out with Datasink
    ds=pe.Node(interface=io.DataSink(),name='ds')
    ds.inputs.base_directory=SinkDir


    #TODO_ready: some plot for qualitiy checking

    # Create workflow
    analysisflow = pe.Workflow(wf_name)
    ###Calculating mean Framewise Displacement (FD) as Power et al., 2012
    # Calculating frames to exclude and include after scrubbing
    analysisflow.connect(inputspec, 'FD', calc_upprperc, 'in_file')
    analysisflow.connect(inputspec, 'threshold', calc_upprperc, 'threshold')
    # Create the proper format for the scrubbing procedure
    analysisflow.connect(calc_upprperc, 'frames_in_idx', craft_scrub_input, 'frames_in_1D_file')
    analysisflow.connect(calc_upprperc, 'out_file', ds, 'percentFD') # TODO save this in separet folder for QC
    analysisflow.connect(inputspec, 'func', craft_scrub_input, 'scrub_input')
    # Do the scubbing
    analysisflow.connect(craft_scrub_input, 'scrub_input_string', scrubbed_preprocessed, 'scrub_input')
    # Output
    analysisflow.connect(scrubbed_preprocessed, 'scrubbed_image', outputspec, 'scrubbed_image')
    analysisflow.connect(inputspec, 'FD', outputspec, 'FD') #TODO: scrub FD file, as well
    # Save a few files
    #analysisflow.connect(scrubbed_preprocessed, 'scrubbed_image', ds, 'scrubbed_image')
    #analysisflow.connect(calc_upprperc, 'percentFD', ds, 'scrubbed_image.@numberofvols')
    analysisflow.connect(scrubbed_preprocessed, 'scrubbed_image', myqc, 'inputspec.func')


    return analysisflow

def datacens_workflow_threshold(SinkTag="func_preproc", wf_name="data_censoring", ex_before=1, ex_after=2):

    """

        Modified version of CPAC.scrubbing.scrubbing +
                            CPAC.generate_motion_statistics.generate_motion_statistics +
                            CPAC.func_preproc.func_preproc

    `source: https://fcp-indi.github.io/docs/developer/_modules/CPAC/scrubbing/scrubbing.html`
    `source: https://fcp-indi.github.io/docs/developer/_modules/CPAC/generate_motion_statistics/generate_motion_statistics.html`
    `source: https://fcp-indi.github.io/docs/developer/_modules/CPAC/func_preproc/func_preproc.html`

    Description:
        Do the data censoring on the 4D functional data. First, it calculates the framewise displacement according to Power's method. Second, it
        indexes the volumes which FD is in the upper part in percent(determined by the threshold variable which is 5% by default). Thirdly, it excludes those volumes and one volume
        before and 2 volumes after the indexed volume. The workflow returns a 4D scrubbed functional data.

    Workflow inputs:
        :param func: The reoriented,motion occrected, nuissance removed and bandpass filtered functional file.
        :param FD: the frame wise displacement calculated by the MotionCorrecter.py script
        :param threshold: threshold of FD volumes which should be excluded
        :param SinkDir:
        :param SinkTag: The output directory in which the returned images (see workflow outputs) could be found in a subdirectory directory specific for this workflow..

    Workflow outputs:

        :return: datacens_workflow - workflow




    Balint Kincses
    kincses.balint@med.u-szeged.hu
    2018


    References
    ----------

    .. [1] Power, J. D., Barnes, K. A., Snyder, A. Z., Schlaggar, B. L., & Petersen, S. E. (2012). Spurious
           but systematic correlations in functional connectivity MRI networks arise from subject motion. NeuroImage, 59(3),
           2142-2154. doi:10.1016/j.neuroimage.2011.10.018

    .. [2] Power, J. D., Barnes, K. A., Snyder, A. Z., Schlaggar, B. L., & Petersen, S. E. (2012). Steps
           toward optimizing motion artifact removal in functional connectivity MRI; a reply to Carp.
           NeuroImage. doi:10.1016/j.neuroimage.2012.03.017

    .. [3] Jenkinson, M., Bannister, P., Brady, M., Smith, S., 2002. Improved optimization for the robust
           and accurate linear registration and motion correction of brain images. Neuroimage 17, 825-841.

    """


    import os
    import nipype
    import nipype.pipeline as pe
    import nipype.interfaces.utility as utility
    import nipype.interfaces.io as io
    import PUMI.utils.utils_convert as utils_convert
    import PUMI.utils.globals as globals
    import PUMI.utils.QC as qc

    SinkDir = os.path.abspath(globals._SinkDir_ + "/" + SinkTag)
    if not os.path.exists(SinkDir):
        os.makedirs(SinkDir)

    # Identitiy mapping for input variables
    inputspec = pe.Node(utility.IdentityInterface(fields=['func',
                                                          'FD',
                                                          'threshold']),
                        name='inputspec')
    inputspec.inputs.threshold = 0.2 #mm

    #TODO_ready check CPAC.generate_motion_statistics.generate_motion_statistics script. It may use the FD of Jenkinson to index volumes which violate the upper threhold limit, no matter what we set.
    # - we use the power method to calculate FD
    above_thr = pe.MapNode(utility.Function(input_names=['in_file',
                                                        'threshold',
                                                         'frames_before',
                                                         'frames_after'],
                                           output_names=['frames_in_idx', 'frames_out_idx', 'percentFD', 'percent_scrubbed_file', 'fd_scrubbed_file', 'nvol'],
                                           function=above_threshold),
                               iterfield=['in_file'],
                             name='above_threshold')
    above_thr.inputs.frames_before = ex_before
    above_thr.inputs.frames_after = ex_after

    # Save outputs which are important
    ds_fd_scrub = pe.Node(interface=io.DataSink(),
                         name='ds_fd_scrub')
    ds_fd_scrub.inputs.base_directory = SinkDir
    ds_fd_scrub.inputs.regexp_substitutions = [("(\/)[^\/]*$", "FD_scrubbed.csv")]
    pop_perc_scrub = pe.Node(interface=utils_convert.List2TxtFileOpen,
                     name='pop_perc_scrub')

    # save data out with Datasink
    ds_pop_perc_scrub = pe.Node(interface=io.DataSink(), name='ds_pop_perc_scrub')
    ds_pop_perc_scrub.inputs.regexp_substitutions = [("(\/)[^\/]*$", "pop_percent_scrubbed.txt")]
    ds_pop_perc_scrub.inputs.base_directory = SinkDir

    # Generate the weird input for the scrubbing procedure which is done in afni
    craft_scrub_input = pe.MapNode(utility.Function(input_names=['scrub_input', 'frames_in_1D_file'],
                                              output_names=['scrub_input_string'],
                                              function=get_indx),
                                   iterfield=['scrub_input', 'frames_in_1D_file'],
                                name='scrubbing_craft_input_string')
    # Scrub the image
    scrubbed_preprocessed = pe.MapNode(utility.Function(input_names=['scrub_input'],
                                                  output_names=['scrubbed_image'],
                                                  function=scrub_image),
                                       iterfield=['scrub_input'],
                                    name='scrubbed_preprocessed')

    myqc = qc.timecourse2png("timeseries", tag="040_censored")

    outputspec = pe.Node(utility.IdentityInterface(fields=['scrubbed_image', 'FD_scrubbed']),
                         name='outputspec')

    # save data out with Datasink
    ds=pe.Node(interface=io.DataSink(),name='ds')
    ds.inputs.base_directory=SinkDir


    #TODO_ready: some plot for qualitiy checking

    # Create workflow
    analysisflow = pe.Workflow(wf_name)
    ###Calculating mean Framewise Displacement (FD) as Power et al., 2012
    # Calculating frames to exclude and include after scrubbing
    analysisflow.connect(inputspec, 'FD', above_thr, 'in_file')
    analysisflow.connect(inputspec, 'threshold', above_thr, 'threshold')
    # Create the proper format for the scrubbing procedure
    analysisflow.connect(above_thr, 'frames_in_idx', craft_scrub_input, 'frames_in_1D_file')
    analysisflow.connect(above_thr, 'percent_scrubbed_file', ds, 'percentFD') # TODO save this in separate folder for QC
    analysisflow.connect(inputspec, 'func', craft_scrub_input, 'scrub_input')
    # Do the scubbing
    analysisflow.connect(craft_scrub_input, 'scrub_input_string', scrubbed_preprocessed, 'scrub_input')
    # Output
    analysisflow.connect(scrubbed_preprocessed, 'scrubbed_image', outputspec, 'scrubbed_image')
    analysisflow.connect(above_thr, 'fd_scrubbed_file', outputspec, 'FD_scrubbed') #TODO_ready: scrub FD file, as well
    analysisflow.connect(above_thr, 'fd_scrubbed_file', ds_fd_scrub, 'FD_scrubbed')

    analysisflow.connect(above_thr, 'percent_scrubbed_file', pop_perc_scrub, 'in_list')
    analysisflow.connect(pop_perc_scrub, 'txt_file', ds_pop_perc_scrub, 'pop')

    # Save a few files
    analysisflow.connect(scrubbed_preprocessed, 'scrubbed_image', ds, 'scrubbed_image')
    #analysisflow.connect(above_thr, 'percentFD', ds, 'scrubbed_image.@numberofvols')
    analysisflow.connect(scrubbed_preprocessed, 'scrubbed_image', myqc, 'inputspec.func')


    return analysisflow


def spikereg_workflow(SinkTag="func_preproc", wf_name="data_censoring_despike"):

    """

    Description:
        Calculates volumes to be excluded, creates the despike regressor matrix

    Workflow inputs:
        :param FD: the frame wise displacement calculated by the MotionCorrecter.py script
        :param threshold: threshold of FD volumes which should be excluded
        :param SinkDir:
        :param SinkTag: The output directory in which the returned images (see workflow outputs) could be found in a subdirectory directory specific for this workflow..

    Workflow outputs:

        :return: spikereg_workflow - workflow

    Tamas Spisak
    tamas.spisak@uk-essen.de
    2018


    References
    ----------

    .. [1] Power, J. D., Barnes, K. A., Snyder, A. Z., Schlaggar, B. L., & Petersen, S. E. (2012). Spurious
           but systematic correlations in functional connectivity MRI networks arise from subject motion. NeuroImage, 59(3),
           2142-2154. doi:10.1016/j.neuroimage.2011.10.018

    .. [2] Power, J. D., Barnes, K. A., Snyder, A. Z., Schlaggar, B. L., & Petersen, S. E. (2012). Steps
           toward optimizing motion artifact removal in functional connectivity MRI; a reply to Carp.
           NeuroImage. doi:10.1016/j.neuroimage.2012.03.017

    .. [3] Jenkinson, M., Bannister, P., Brady, M., Smith, S., 2002. Improved optimization for the robust
           and accuratedef datacens_workflow(SinkTag="func_preproc", wf_name="data_censoring"):

    """
    import os
    import nipype
    import nipype.pipeline as pe
    import nipype.interfaces.utility as utility
    import nipype.interfaces.io as io
    import PUMI.utils.globals as globals
    import PUMI.utils.QC as qc

    SinkDir = os.path.abspath(globals._SinkDir_ + "/" + SinkTag)
    if not os.path.exists(SinkDir):
        os.makedirs(SinkDir)

    # Identitiy mapping for input variables
    inputspec = pe.Node(utility.IdentityInterface(fields=['func',
                                                          'FD',
                                                          'threshold',]),
                        name='inputspec')
    inputspec.inputs.threshold = 5

    #TODO_ready check CPAC.generate_motion_statistics.generate_motion_statistics script. It may use the FD of Jenkinson to index volumes which violate the upper threhold limit, no matter what we set.
    # - we use the power method to calculate FD
    # Determine the indices of the upper part (which is defined by the threshold, deafult 5%) of values based on their FD values
    calc_upprperc = pe.MapNode(utility.Function(input_names=['in_file',
                                                        'threshold'],
                                           output_names=['frames_in_idx', 'frames_out_idx', 'percentFD', 'out_file', 'nvol'],
                                           function=calculate_upperpercent),
                               iterfield=['in_file'],
                             name='calculate_upperpercent')

    #create despiking matrix, to be included into nuisance correction
    despike_matrix = pe.MapNode(utility.Function(input_names=['frames_excluded', 'total_vols'],
                                           output_names=['despike_mat'],
                                           function=create_despike_regressor_matrix),
                               iterfield=['frames_excluded', 'total_vols'],
                             name='create_despike_matrix')

    outputspec = pe.Node(utility.IdentityInterface(fields=['despike_mat', 'FD']),
                         name='outputspec')

    # save data out with Datasink
    ds=pe.Node(interface=io.DataSink(),name='ds')
    ds.inputs.base_directory=SinkDir


    #TODO_ready: some plot for qualitiy checking

    # Create workflow
    analysisflow = pe.Workflow(wf_name)
    ###Calculating mean Framewise Displacement (FD) as Power et al., 2012
    # Calculating frames to exclude and include after scrubbing
    analysisflow.connect(inputspec, 'FD', calc_upprperc, 'in_file')
    analysisflow.connect(inputspec, 'threshold', calc_upprperc, 'threshold')
    # Create the proper format for the scrubbing procedure
    analysisflow.connect(calc_upprperc, 'frames_out_idx', despike_matrix, 'frames_excluded')
    analysisflow.connect(calc_upprperc, 'nvol', despike_matrix, 'total_vols')
    analysisflow.connect(calc_upprperc, 'out_file', ds, 'percentFD') # TODO save this in separet folder for QC
    # Output
    analysisflow.connect(despike_matrix, 'despike_mat', outputspec, 'despike_mat')
    analysisflow.connect(inputspec, 'FD', outputspec, 'FD')
    return analysisflow

def above_threshold(in_file, threshold=0.2, frames_before=1, frames_after=2):
    import os
    import numpy as np
    from numpy import loadtxt, savetxt
    powersFD_data = loadtxt(in_file, skiprows=1)
    np.insert(powersFD_data, 0, 0)  # TODO_ready: why do we need this: see output of nipype.algorithms.confounds.FramewiseDisplacement
    frames_in_idx = np.argwhere(powersFD_data < threshold)[:, 0]
    frames_out = np.argwhere(powersFD_data >= threshold)[:, 0]

    extra_indices = []
    for i in frames_out:

        # remove preceding frames
        if i > 0:
            count = 1
            while count <= frames_before:
                extra_indices.append(i - count)
                count += 1

        # remove following frames
        count = 1
        while count <= frames_after:
            if i+count < len(powersFD_data):  # do not censor unexistent data
                extra_indices.append(i + count)
            count += 1
    indices_out = list(set(frames_out) | set(extra_indices))
    indices_out.sort()

    frames_out_idx = indices_out
    frames_in_idx = np.setdiff1d(frames_in_idx, indices_out)

    FD_scrubbed = powersFD_data[frames_in_idx]
    fd_scrubbed_file = os.path.join(os.getcwd(), 'FD_scrubbed.csv')
    savetxt(fd_scrubbed_file, FD_scrubbed, delimiter=",")

    frames_in_idx_str = ','.join(str(x) for x in frames_in_idx)
    frames_in_idx = frames_in_idx_str.split()

    percentFD = (len(frames_out_idx) * 100 / (len(powersFD_data) + 1)) # % of frames censored
    percent_scrubbed_file = os.path.join(os.getcwd(), 'percent_scrubbed.txt')
    f = open(percent_scrubbed_file, 'w')
    f.write("%.3f" % (percentFD))
    f.close()

    nvol = len(powersFD_data)

    return frames_in_idx, frames_out_idx, percentFD, percent_scrubbed_file, fd_scrubbed_file, nvol



def calculate_upperpercent(in_file,threshold, frames_before=1, frames_after=2):
    import os
    import numpy as np
    from numpy import loadtxt
    # Receives the FD file to calculate the upper percent of violating volumes
    powersFD_data = loadtxt(in_file, skiprows=1)
    np.insert(powersFD_data, 0, 0)  # TODO_ready: why do we need this: see output of nipype.algorithms.confounds.FramewiseDisplacement
    sortedpwrsFDdata = sorted(powersFD_data)
    limitvalueindex = int(len(sortedpwrsFDdata) * threshold / 100)
    limitvalue = sortedpwrsFDdata[len(sortedpwrsFDdata) - limitvalueindex]
    frames_in_idx = np.argwhere(powersFD_data < limitvalue)[:,0]
    frames_out = np.argwhere(powersFD_data >= limitvalue)[:, 0]
    extra_indices = []
    for i in frames_out:

        # remove preceding frames
        if i > 0:
            count = 1
            while count <= frames_before:
                extra_indices.append(i - count)
                count += 1

        # remove following frames
        count = 1
        while count <= frames_after:
            if i+count < len(powersFD_data):  # do not censor unexistent data
                extra_indices.append(i + count)
            count += 1

    indices_out = list(set(frames_out) | set(extra_indices))
    indices_out.sort()
    frames_out_idx=indices_out
    frames_in_idx=np.setdiff1d(frames_in_idx, indices_out)
    frames_in_idx_str = ','.join(str(x) for x in frames_in_idx)
    frames_in_idx = frames_in_idx_str.split()


    percentFD =100- (len(frames_out_idx) * 100 / (len(powersFD_data) + 1))

    out_file = os.path.join(os.getcwd(), 'numberofcensoredvolumes.txt')
    f = open(out_file, 'w')
    f.write("%.3f," % (percentFD))
    f.close()

    nvol=len(powersFD_data)

    return frames_in_idx, frames_out_idx, percentFD, out_file, nvol

def get_indx(scrub_input, frames_in_1D_file):
    """
    Method to get the list of time
    frames that are to be included

    Parameters
    ----------
    in_file : string
        path to file containing the valid time frames

    Returns
    -------
    scrub_input_string : string
        input string for 3dCalc in scrubbing workflow,
        looks something like " 4dfile.nii.gz[0,1,2,..100] "

    """

    #f = open(frames_in_1D_file, 'r')
    #line = f.readline()
    #line = line.strip(',')
    frames_in_idx_str = '[' + ','.join(str(x) for x in frames_in_1D_file) + ']'
    #if line:
    #    indx = map(int, line.split(","))
    #else:
     #   raise Exception("No time points remaining after scrubbing.")
    #f.close()

    #scrub_input_string = scrub_input + str(indx).replace(" ", "")
    scrub_input_string = scrub_input + frames_in_idx_str
    return scrub_input_string

def scrub_image(scrub_input):
    """
    Method to run 3dcalc in order to scrub the image. This is used instead of
    the Nipype interface for 3dcalc because functionality is needed for
    specifying an input file with specifically-selected volumes. For example:
        input.nii.gz[2,3,4,..98], etc.

    Parameters
    ----------
    scrub_input : string
        path to 4D file to be scrubbed, plus with selected volumes to be
        included

    Returns
    -------
    scrubbed_image : string
        path to the scrubbed 4D file

    """

    import os

    os.system("3dcalc -a %s -expr 'a' -prefix scrubbed_preprocessed.nii.gz" % scrub_input)

    scrubbed_image = os.path.join(os.getcwd(), "scrubbed_preprocessed.nii.gz")

    return scrubbed_image

def create_despike_regressor_matrix(frames_excluded, total_vols):
    # adapted from C-PAC
    """Create a Numpy array describing which volumes are to be regressed out
    during nuisance regression, for de-spiking.
    :param frames_excluded: 1D file of the volume indices to be excluded. This
    is a 1D text file of integers separated by commas.
    :param total_vols: integer value of the length of the time series (number
    of volumes).
    :return: tsv file consisting of a row for every volume, and a column
    for every volume being regressed out, with a 1 where they match.
    """

    import numpy as np
    import os

    #with open(frames_excluded, 'r') as f:
    #    excl_vols = f.readlines()

    excl_vols=frames_excluded

    if len(excl_vols) <= 0:
        return None

    reg_matrix = np.zeros((total_vols, len(excl_vols)), dtype=int)

    i = 0
    for vol in excl_vols:
        reg_matrix[vol][i] = 1
        i += 1

    np.savetxt("despike_matrix.csv", reg_matrix)

    return os.path.join(os.getcwd(),"despike_matrix.csv")

