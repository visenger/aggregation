#!/usr/bin/env python
__author__ = 'greghines'
import numpy as np
import os
import pymongo
import sys
import urllib
import matplotlib.cbook as cbook
from PIL import Image
import matplotlib.pyplot as plt
import warnings

if os.path.exists("/home/ggdhines"):
    sys.path.append("/home/ggdhines/PycharmProjects/reduction/experimental/clusteringAlg")
else:
    sys.path.append("/home/greg/github/reduction/experimental/clusteringAlg")
#from divisiveDBSCAN import DivisiveDBSCAN
from divisiveDBSCAN_multi import DivisiveDBSCAN
from clusterCompare import cluster_compare

if os.path.exists("/home/ggdhines"):
    base_directory = "/home/ggdhines"
else:
    base_directory = "/home/greg"

client = pymongo.MongoClient()
db = client['penguin_2014-10-12']
collection = db["penguin_classifications"]
collection2 = db["penguin_subjects"]

steps = [5,20]
penguins_at = {k:[] for k in steps}
alreadyThere = False
subject_index = 0
import cPickle as pickle
to_sample = pickle.load(open(base_directory+"/Databases/sample.pickle","rb"))
import random
#for subject in collection2.find({"classification_count": 20}):
noise_list = {k:[] for k in steps}
less_than_30 = 0
specific_users = set([])
users_results_1 = {}
users_results_2 = {}
for zooniverse_id in random.sample(to_sample,len(to_sample)):
    #zooniverse_id = "APZ00010ep"
    subject = collection2.find_one({"zooniverse_id": zooniverse_id})
    subject_index += 1
    #if subject_index == 2:
    #    break
    #zooniverse_id = subject["zooniverse_id"]
    print "=== " + str(subject_index)
    print zooniverse_id

    alreadyThere = True
    user_markings = {k:[] for k in steps}
    user_ips = {k:[] for k in steps}
    penguins_tagged = []
    user_index = 0
    for classification in collection.find({"subjects" : {"$elemMatch": {"zooniverse_id":zooniverse_id}}}):
        user_index += 1
        if user_index == 21:
            break

        per_user = []

        ip = classification["user_ip"]
        tt = 0
        try:
            markings_list = classification["annotations"][1]["value"]
            if isinstance(markings_list,dict):
                for marking in markings_list.values():
                    if marking["value"] in ["adult","chick"]:
                        x,y = (float(marking["x"]),float(marking["y"]))
                        if not((x,y) in per_user):
                            per_user.append((x,y))
                            for s in steps:
                                if user_index <= s:
                                    user_markings[s].append((x,y))
                                    user_ips[s].append(ip)

                            tt += 1

        except (KeyError, ValueError):
                #classification["annotations"]
                user_index += -1

        penguins_tagged.append(tt)
    if user_markings[5] == []:
        print "skipping empty"
        subject_index += -1
        continue

    url = subject["location"]["standard"]
    object_id= str(subject["_id"])
    image_path = base_directory+"/Databases/penguins/images/"+object_id+".JPG"
    if not(os.path.isfile(image_path)):
        urllib.urlretrieve(url, image_path)

    penguins = []
    penguins_center = {}
    noise_points = {}
    try:
        for s in steps:
            if s == 25:
                user_identified_penguins,penguin_clusters,noise__ = DivisiveDBSCAN(3).fit(user_markings[s],user_ips[s],debug=True,jpeg_file=base_directory + "/Databases/penguins/images/"+object_id+".JPG")
            else:
                user_identified_penguins,penguin_clusters,noise__ = DivisiveDBSCAN(1).fit(user_markings[s],user_ips[s],debug=True)



            penguins_at[s].append(len(user_identified_penguins))
            penguins_center[s] = user_identified_penguins
            #noise_list[s].append(noise)

            penguins.append(penguin_clusters)
            #print penguin_clusters
            #print noise__
            noise_points[s] = [x for x,u in noise__]
            print str(s) + "  -  " + str(len(user_identified_penguins))

            if len(user_identified_penguins) > 30:
                break
    except AssertionError:
        continue

    #if len(user_identified_penguins) == 0:
    #    continue
    if penguins_at[5][-1] == 0:
        continue

    if len(user_identified_penguins) <= 30:
        print [len(p) for p in penguins[0]]
        votes = [len(p)/5. for p in penguins[0]]

        user_list = []
        for p in penguins[0]:
            indices = [user_markings[5].index(X) for X in p]
            user_list.append([user_ips[5][i] for i in indices])

        for u in set(user_ips[5]):
            V = [v for i,v in enumerate(votes) if u in user_list[i]]
            if V != []:
                mean_weight = np.mean(V)
            else:
                mean_weight = 0
            if not(u in users_results_1):
                users_results_1[u] = [mean_weight]
            else:
                users_results_1[u].append(mean_weight)


            V2 = [v for i,v in enumerate(votes) if not(u in user_list[i])]
            if V2 != []:
                mean_weight = np.mean(V2)
            else:
                mean_weight = 0
            if not(u in users_results_2):
                users_results_2[u] = [mean_weight]
            else:
                users_results_2[u].append(mean_weight)

        print "===="

        less_than_30 += 1
        print less_than_30

    if less_than_30 == 100:
        break

print "==========="
print "==========="
for u in users_results_1.keys():
    if u in users_results_2.keys():
        plt.plot(np.mean(users_results_1[u]),np.mean(users_results_2[u]),'.',color="blue")

plt.show()