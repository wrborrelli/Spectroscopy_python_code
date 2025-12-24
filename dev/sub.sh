#! /bin/bash
#USER VARIABLES:
#$ -l h_rt=24:00:00,h_data=10G
#$ -N tb2DES
#$ -S /bin/bash      
#$ -o $JOB_NAME.out
#$ -e $JOB_NAME.err
#$ -cwd

. /u/local/Modules/default/init/modules.sh
module load anaconda3

conda activate chgnet

python generate_spectra.py input_file >> spec.out

