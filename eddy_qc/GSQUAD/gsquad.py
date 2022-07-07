from __future__ import division

import datetime
import os
import warnings

import numpy as np
import matplotlib
import matplotlib.style
from matplotlib.backends.backend_pdf import PdfPages

warnings.filterwarnings("ignore")
matplotlib.use('Agg')   # generate pdf output by default
matplotlib.interactive(False)
matplotlib.style.use('classic')

from eddy_qc.GSQUAD import (gsquad_report, gsquad_var, gsquad_db, gsquad_update)
from eddy_qc.utils import (utils, ref_page)


#=========================================================================================
# FSL EDDY SQUAD (Study-wise QUality Assessment for DMRI)
# Matteo Bastiani
# 01-06-2017, FMRIB, Oxford
#=========================================================================================
def main(sList, gVar, gDbVar, uOpt, oDir):
    """
    Generate a QC report pdf for group dMRI data.
    The script will loop through the specified qc.json files obtained using eddy_squad on 
    a set of subjects. It will produce a report pdf showing the distributions of the qc indices
    if found in the .json files. If a grouping variable is provided, extra pages will show different 
    distributions according to the grouping variable specified. If the update flag is set to true, it 
    will also update the single subject qc reports putting them into the context of the larger group. 
    Lastly, it will store the qc indices for all subjects to create a database for
    future use.

    Compulsory arguments:
       list                          Text file containing a list of squad qc folders
   
    Optional arguments:
       -g, --grouping                Text file containing grouping variable for the listed subjects
       -u, --update [group_db.json]  Update existing eddy_squad reports after generating group report or using a pre-existing [group_db.json] one
       -gdb, --group-db              Text file containing grouping variable for the database subjects
       -o, --output-dir              Output directory - default = '<eddyBase>.qc' 
    
    Output:
       output-dir/group_qc.pdf: study-wise QC report 
       output-dir/group_db.json: study-wise QC database
    """

    # Check inputs
    if not os.path.isfile(sList):
        raise ValueError(sList + ' does not appear to be a valid subject qc folders list file')
    if gVar is not None and os.path.isfile(gVar):
        group = np.genfromtxt(gVar, dtype=None, names=True)
    else:
        group = False
    if gDbVar is not None and os.path.isfile(gDbVar):
        group_db = np.genfromtxt(gDbVar, dtype=None, names=True)
        if group_db[group_db.dtype.names[0]][0] != group[group.dtype.names[0]][0]:
            raise ValueError('The two grouping variables categories do not match')
    else:
        group_db = False
    
    #================================================
    # If requested, update the single subject reports
    #================================================
    if (uOpt == 1 or
        uOpt == 2):
        
        # Check if output directory exists
        if oDir is not None:
            out_dir = oDir
        else:
            out_dir = os.getcwd() + '/squad'
        if os.path.exists(out_dir):
            raise ValueError(out_dir + ' directory already exists! Please specify a different one.')

        # Start generating the group database
        print('Generating group database...')

        # Get eddy references
        data = {'qc_path':out_dir}
        ec = utils.EddyCommand(' ', 'squad')
        
        #=========================================================================================
        # Directory and group QC database creation.
        #=========================================================================================
        os.makedirs(out_dir)
        db = gsquad_db.main(out_dir + '/group_db.json', 'w', sList)
        print('Group database generated and stored. Writing group QC report...')

        #================================================
        # Add pages to QC report if information is there
        #================================================
        # Initialize group QC pdf
        pp = PdfPages(out_dir + '/group_qc.pdf')        
        
        # Add pages and, if needed, group indices
        ref_page.main(pp, data, ec)
        gsquad_report.main(pp, db, group, None)
        if group is not False:
            gsquad_var.main(pp, db, group, None, None)
        
        # Set the file's metadata via the PdfPages object:
        d = pp.infodict()
        d['Title'] = 'eddy_squad QC report'
        d['Author'] = u'Matteo Bastiani'
        d['Subject'] = 'group QC report'
        d['Keywords'] = 'QC dMRI'
        d['CreationDate'] = datetime.datetime.today()
        d['ModDate'] = datetime.datetime.today()

        # Close file
        pp.close()
        print('Group QC report generated')
        
        # If set, update single subject reports
        if uOpt == 2:
            print('Updating single subject reports...')
            gsquad_update.main(db, sList, group, group_db)
            print('Single subject QC reports updated')
    else:
        # Read group database
        print('Reading group database...')
        db = gsquad_db.main(uOpt, 'r', None)
        print('Group database imported.')

        # Update single subject reports
        print('Updating single subject reports...')
        gsquad_update.main(db, sList, group, group_db)
        print('Single subject QC reports updated')
        
    