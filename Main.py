# Copyright 2018 Johanan Idicula
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import datetime as dt
import glob
import os
import re
from fnmatch import fnmatch
import multiprocessing as mp
import time

import imgutil as imgu
import metadatautil as mu
import inpututil as inputu

start = time.time()

# File selector
exp_loc_prompt = str("Enter the full filepath to the experiment directory" +
                     " containing Position directories with TIFFs: ")
exp_loc = inputu.input_regex(exp_loc_prompt, "[^\0]+", "Invalid filepath")
# exp_loc = "/home/jidicula/johanan/prog/test/Mark_and_Find_001"

n_frames_prompt = "Number of frames in a sequence: "
n_frames = int(inputu.input_regex(n_frames_prompt, "\d+", "Not an integer!"))

nuc_channel_prompt = "Which channel has the NLS protein? 0/1/2/3: "
nuc_channel = inputu.input_regex(nuc_channel_prompt, "[0-3]", "Not a channel!")
nuc_channel = "{:02d}".format(int(nuc_channel))

poi_channel_prompt = "Which channel has the POI? 0/1/2/3: "
poi_channel = inputu.input_regex(poi_channel_prompt, "[0-3]", "Not a channel!")
poi_channel = "{:02d}".format(int(poi_channel))
# nuc_channel = "01"
# poi_channel = "00"
# n_frames = 71

cpu_count = mp.cpu_count()

if cpu_count > 2:
    cpu_num = int(cpu_count) - 2  # Be nice, leave 2 cores free.
else:
    cpu_num = 1

print(dt.datetime.now(), "Data location:\n ", exp_loc)
positions = glob.glob(exp_loc + '/Position*')  # list of full filepaths
positions.sort()
n_pos = len(positions)
first_md_path = glob.glob(positions[0] + "/MetaData/*_Properties.xml")
first_time = mu.get_time(first_md_path[0], 0)


def analyzer(filepath_prefix):
    analysis_start = time.time()
    current_frame = filepath_prefix.split("/")[-1]
    print(str(dt.datetime.now()), "Analyzing {}".format(current_frame))
    # filepath construction
    poi_filepath = filepath_prefix + '_ch' + poi_channel + '.tif'
    nuc_filepath = filepath_prefix + '_ch' + nuc_channel + '.tif'
    # timestamp generation
    # Need to retrieve first time from first_time.txt
    # with open("first_time.txt", "r") as time_read_f:
    #     first_time_string = time_read_f.read()
    # first_time = dt.datetime.strptime(first_time_string,
    #                                   "%Y-%m-%d %H:%M:%S.%f")
    position_name = filepath_prefix.split("/")[-2]
    metadata_path = re.sub("Position\d{3}_t.*", '', filepath_prefix) + \
        "MetaData/" + position_name + "_Properties.xml"
    frame_num = filepath_prefix.split("_")[-1].split("t")[-1]
    # microns per pixel scale
    scale = mu.get_scale(metadata_path)
    results_filename = "Results/" + position_name + \
                       '_t' + str(frame_num) + '.csv'
    # mask generation
    try:
        poi_mask = imgu.mask_gen(poi_filepath)[-1]
        nuc_mask = imgu.mask_gen(nuc_filepath)[-1]
        timestamp = mu.get_time(metadata_path, int(frame_num))
    except Exception as err:
        with open(results_filename, "w") as result_csv:
            result_csv.write("," + "," + "," + ",")
            print(str(dt.datetime.now()),
                  "{0}: wrote null values for {1}".format(err,
                                                          filepath_prefix))
        return
    elapsed_time = timestamp - first_time
    # segmentation
    cyto, cyto_sum, nuc, nuc_sum = imgu.mask_segmenter(nuc_mask, poi_filepath)
    imgu.img_writer("Results/img/" + position_name + '_t' +
                    str(frame_num) + "_cyto", cyto)
    imgu.img_writer("Results/img/" + position_name + '_t' +
                    str(frame_num) + "_nuc", nuc)
    try:
        fluo_ratio = round(float(nuc_sum) / float(cyto_sum), 3)
    except ZeroDivisionError:
        fluo_ratio = ''
    if fluo_ratio == 0.0:
        with open(results_filename, "w") as result_csv:
            result_csv.write("," + "," + "," + ",")
            print(str(dt.datetime.now()),
                  "Ratio = 0: wrote null values for {}".format(
                      filepath_prefix))
        return
    poi_label = imgu.img_labeler(poi_mask)
    poi_area = imgu.area_measure(poi_label) * scale
    poi_aspect_ratio = round(imgu.aspect_ratio(poi_label), 3)
    nuc_area = imgu.area_measure(imgu.img_labeler(nuc_mask)) * scale
    minutes = round(elapsed_time.total_seconds()/60.0, 3)
    # Writes to Results/PositionXXtYY.csv in the form:
    # minutes, fluorescence ratio, POI aspect ratio, POI area, nucleus area
    with open(results_filename, "w") as result_csv:
        result_csv.write(str(minutes) + "," + str(fluo_ratio) + "," +
                         str(poi_aspect_ratio) + "," + str(poi_area) +
                         "," + str(nuc_area))
    analysis_end = time.time()
    analysis_time = round((analysis_end - analysis_start)/60, 3)
    print(str(dt.datetime.now()),
          "Wrote {0} in {1} minutes.".format(results_filename, analysis_time))


pattern = "*.tif"
img_filepaths = []
for path, subdirs, files in os.walk(exp_loc):
    for name in files:
        if fnmatch(name, pattern):
            img_filepaths.append(os.path.join(path, name))
for k, filepath in enumerate(img_filepaths):
    new_filepath = re.sub('_ch.*', '', filepath)
    img_filepaths[k] = new_filepath

# Making the process worker pool.
if __name__ == '__main__':
    with mp.Pool(processes=(cpu_num)) as pool:
        pool.map(analyzer, img_filepaths)

# Coalesce all the result csv files into one
print("hello there")
with open("Results/results.csv", "w") as f:
    f.write("Cell")
    for i in range(n_frames):
        f.write(",t" + str(i))  # time
        f.write(",f" + str(i))  # fluorescence ratio
        f.write(",ar" + str(i))  # aspect ratio
        f.write(",ca" + str(i))  # cell area
        f.write(",na" + str(i))  # nucleus area
    f.write("\n")
# TODO: read in all mini csv files into main results.csv
# Subdivide into position sublists, then read each one individually?
position_filenames = []
for position in positions:
    position_filenames.append(position.split('/')[-1])

for idx, position_fn in enumerate(position_filenames):
    position_results = []
    for l in range(n_frames):
        result_filepath = str(
            "Results/" + position_fn +
            str('_t{:0' + str(len(str(n_frames-1))) + 'd}.csv').format(l))
        with open(result_filepath, "r") as result_f:
            contents = result_f.read()
        os.remove(result_filepath)
        position_data = re.sub('\]', '', re.sub('\[', '', str(contents)))
        position_data = re.sub(' ', '', position_data)
        position_results.append(position_data)
    position_results_str = re.sub(
        '\]', '', re.sub('\[', '', str(position_results)))
    position_results_str = re.sub(' ', '', position_results_str)
    position_results_str = re.sub("'", "", position_results_str)
    with open("Results/results.csv", "a") as fi:
        fi.write(str(idx + 1) + ',' + position_results_str + '\n')

# Removing trailing comma in each line
with open("Results/results.csv", "r") as res_fi_read:
    full_result_str = res_fi_read.read()
    full_result_str = re.sub(",\n", "\n", full_result_str)
    full_result_str = full_result_str[:-1]

# Rewriting results.csv
os.remove("Results/results.csv")
with open("Results/results.csv", "w") as res_file_write:
    res_file_write.write(full_result_str)

print(str(dt.datetime.now()), "Wrote Results/results.csv")

end = time.time()
print(str(dt.datetime.now()), "Runtime:", str(
    round((end-start)/3600.0, 3)), "hours")
