#!/usr/bin/env python

import os
import pwd
import sys
import time
import file_paths_config as paths
from glob import glob
from Pegasus.DAX3 import *

# The name of the DAX file is the first argument
if len(sys.argv) != 2:
        sys.stderr.write("Usage: %s DAXFILE\n" % (sys.argv[0]))
        sys.exit(1)
daxfile = sys.argv[1]

USER = pwd.getpwuid(os.getuid())[0]

# Create a abstract dag
dax = ADAG("split")

# Add some workflow-level metadata
dax.metadata("creator", "%s@%s" % (USER, os.uname()[1]))
dax.metadata("created", time.ctime())

plant_ids = set()
path_list = glob(paths.file_paths['data'])
path_list_index = paths.file_paths['data'].split('/').index('*')
current_dir = os.getcwd()
plant_phenotyping_index = current_dir.split('/').index('plant-phenotyping')
plant_phenotyping_path = "/".join(current_dir.split('/')[:plant_phenotyping_index + 1])
plant_predict_jobs =  {}
plant_extract_jobs = {}
plant_predict_files = {}
model = paths.file_paths['model']
model_str = model.split('.')[0]
model_file = File(model)

for path in sorted(path_list):
	# If hyperspectral images...
	joined_path = "\\\"%s\\\"" % path
	plant_folder_name = path.split('/')[path_list_index]
	if 'npy' != plant_folder_name.split('.')[-1]:
		plant_folder_name = path.split('/')[path_list_index]
		plant_folder_name = plant_folder_name.replace(' ','_')
		plant_name = plant_folder_name.split("_")[2]
		date = plant_folder_name.split("_")[3]
		npy_name = plant_name + "_" + date
		preprocess = Job("python3")
		preprocess.addArguments("-m", "schnablelab.CNN.Preprocess","hyp2arr", joined_path, npy_name)
		dax.addJob(preprocess)
		nparr = File("%s.npy" % npy_name)
		preprocess.uses(nparr, link=Link.OUTPUT, transfer=False, register=True)
		prediction = File("%s.%s.prd.png" % (model_str, npy_name))
		predict = Job("python3")
		predict.addArguments("-m", "schnablelab.CNN.Predict_snn","Predict", model_file, nparr)
		predict.uses(model, link=Link.INPUT)
		predict.uses(nparr, link=Link.INPUT)
		predict.setStdout(prediction)
		predict.uses(prediction, link=Link.OUTPUT, transfer=True, register=True)
		dax.addJob(predict)
		dax.depends(predict, preprocess)
	else:
		numpy_name = plant_folder_name.split('.')[0]
		plant_name = numpy_name.split('_')[0]
		prediction = File("%s.%s.prd.png" % (model_str, numpy_name))
		predict = Job("python3")
		model_file = File(model)
		predict.addArguments("-m", "schnablelab.CNN.Predict_snn","Predict", model_file, path)
		predict.uses(model, link=Link.INPUT)
		predict.setStdout(prediction)
		predict.uses(prediction, link=Link.OUTPUT, transfer=True, register=True)
		dax.addJob(predict)
	if plant_name not in plant_ids:
		plant_ids.add(plant_name)
		measure = Job("python3")
		measure.uses(prediction, link=Link.INPUT)
		plant_extract_jobs[plant_name] = measure
		plant_predict_jobs[plant_name] = [predict]
		plant_predict_files[plant_name] = [prediction]
	else:
		plant_predict_jobs[plant_name].append(predict)
		plant_predict_files[plant_name].append(prediction)
		measure.uses(prediction, link=Link.INPUT)

for plant_name in plant_extract_jobs:
	job = plant_extract_jobs[plant_name]
	csv_name = "plant_traits_" + plant_name + ".csv"
	csv = File(csv_name)
	job.uses(csv, link=Link.OUTPUT, transfer=True, register=True)
	job.setStdout(csv)
	job.addArguments(plant_phenotyping_path + "/traits_extraction.py", "-i", plant_name, "-f", *plant_predict_files[plant_name])
	dax.addJob(job)
	graphs_name = plant_name + "_growth_curve.png"
	graphs = File(graphs_name)
	visualize = Job("python3")
	visualize.addArguments(plant_phenotyping_path + "/visualize.py", "-p", csv)
	visualize.uses(csv, link=Link.INPUT)
	visualize.uses(graphs, link=Link.OUTPUT, transfer=True, register=False)
	dax.addJob(visualize)
	dax.depends(child=visualize, parent=job)
	for predict_job in plant_predict_jobs[plant_name]:
		dax.depends(child=job, parent=predict_job)


f = open(daxfile, "w")
dax.writeXML(f)
f.close()
