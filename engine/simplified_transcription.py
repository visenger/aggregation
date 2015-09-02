#!/usr/bin/env python
__author__ = 'greg'
import clustering
import numpy as np
import re
import os
import transcription
from aggregation_api import hesse_line_reduction
from scipy import spatial
import datetime
import cPickle as pickle

if os.path.exists("/home/ggdhines"):
    base_directory = "/home/ggdhines"
else:
    base_directory = "/home/greg"


class SimplifiedTextCluster(transcription.TextCluster):
    def __init__(self,shape,dim_reduction_alg):
        clustering.Cluster.__init__(self,shape,dim_reduction_alg)

    def __inner_fit__(self,markings,user_ids,tools,reduced_markings):
        # we want to first cluster first just on dist and theta - ignoring the text contents
        # dist_list,theta_list,text_list,raw_pts_list = zip(*markings)
        # mapped_markings = zip(dist_list,theta_list)

        # cluster just on points, not on text
        dist_l,theta_l,text_l = zip(*reduced_markings)
        reduced_markings_without_text = zip(dist_l,theta_l)
        ordering  = self.__fit2__(reduced_markings_without_text,user_ids)

        # use the below 2 to build up each cluster
        current_lines = {}
        current_pts = {}
        clusters = []


        for a,b in ordering:
            # a - line values - "intercept" and slope
            user_index = reduced_markings_without_text.index(a)
            user = user_ids[user_index]
            # extract the corresponding text and the raw (unmapped) point
            # text = text_list[user_index]
            # raw_pt = raw_pts_list[user_index]

            text = markings[user_index][-1]
            raw_pt = markings[user_index][:-1]


            if "\n" in text:
                print "multiline - skipping"
                continue



            # convert from unicode to ascii
            assert isinstance(text,unicode)
            text = text.encode('ascii','ignore')

            # #  # todo - can this be done better?
            # special_characters = {}
            # for tag in ["[notenglish]","[/notenglish]"]:
            #     special_characters[tag] = [match.start() for match in re.finditer(re.escape(tag), text)]
            # print special_characters
            text = re.sub("\[deletion\].*\[/deletion\]","",text)
            text = re.sub(r'\[deletion\].*\[\\deletion\]',"",text)
            text = re.sub("\[illegible\].*\[/illegible\]","",text)
            text = re.sub(r'\[deletionhas\]\[/deletion\]',"",text)
            text = re.sub("\[insertion\].*\[/insertion\]","",text)
            text = re.sub("\[underline\].*\[/underline\]","",text)
            text = re.sub("\[notenglish\].*\[/notenglish\]","",text)
            text = re.sub(r'\[has\]',"",text)
            text = re.sub(r'\(deleted\)',"",text)
            text = re.sub(r'\[deletion\]',"",text)
            text = re.sub("\[insertion\]","",text)

            # todo - find a way to fix this - stupid postgres/json
            text = re.sub(r'\'',"",text)

            # do this now, because all of the above subsitutions may have created an empty line
            if text == "":
                continue

            # if we have an empty cluster, just add the line
            if current_lines == {}:
                current_lines[user] = text #(text,special_characters)

                # adding the user id is slightly redundant but makes doing the actual clustering easier
                current_pts[user] = (raw_pt,user)
            else:
                # need to see if we want to merge
                # do we already have some text from this user for this current cluster?
                # IMPORTANT
                # VERY IMPORTANT
                # for the simplified transcription, we will assume that we should automatically start a new
                # cluster - i.e. we don't deal with split lines
                if user in current_pts:
                    clusters.append((current_lines.values(),current_pts.values()))
                    current_lines = {user:text} #(text,special_characters)}
                    current_pts = {user:(raw_pt,user)}
                else:
                    # does adding this line to the cluster make sense?
                    # compare against the current accuracy - if we only have 1 line so far,
                    # current accuracy is NA
                    users_and_lines = sorted(current_lines.items(),key = lambda x:x[0])
                    sorted_users,sorted_lines = zip(*users_and_lines)
                    # sorted_lines = zip(*sorted_pts)[-1]

                    # uncomment below if you want to compare the new accuracy against the old
                    # if len(current_lines) > 1:
                    #     aligned_text = self.__get_aggregation_lines__(sorted_lines)
                    #     current_accuracy = self.__agreement__(aligned_text)
                    # else:
                    #     current_accuracy = -1

                    # what would the accuracy be if we added in this new user's line?
                    new_lines = list(sorted_lines)
                    assert isinstance(sorted_users,tuple)
                    # user_index = sorted_users.index(user)

                    # start by trying straight up replacing
                    new_lines.append(text)
                    # print sorted_pts
                    # print new_lines
                    new_aligned = self.__get_aggregation_lines__(new_lines)
                    new_accuracy = self.__agreement__(new_aligned)

                    if min(new_accuracy) >= 0.6:
                        current_pts[user] = (raw_pt,user)
                        current_lines[user] = text
                    else:
                        clusters.append((current_lines.values(),current_pts.values()))
                        # current_pts = {user:(pt,text)}
                        current_lines = {user:text}
                        current_pts = {user:(raw_pt,user)}

        clusters.append((current_lines.values(),current_pts.values()))

        # remove any clusters which have only one user
        for cluster_index in range(len(clusters)-1,-1,-1):
            # print len(clusters[cluster_index][0])
            if len(clusters[cluster_index][0]) <= 1: #2
                # assert len(clusters[cluster_index][1]) == 1
                clusters.pop(cluster_index)

        if len(clusters) == 0:
            return [],0

        # if we have more than one cluster - some of them might need to be merged
        # after removing "error" cluster
        # to do so - revert back to Hesse format
        if len(clusters) > 1:

            hessen_lines = []

            for cluster_index in range(len(clusters)):
                lines_segments,users = zip(*clusters[cluster_index][1])
                x1_l, x2_l, y1_l, y2_l = zip(*lines_segments)
                x1,x2,y1,y2 = np.median(x1_l),np.median(x2_l),np.median(y1_l),np.median(y2_l)
                hessen_lines.append(hesse_line_reduction([[x1,x2,y1,y2],])[0])

            # print hessen_lines
            slope_l,angle_l = zip(*hessen_lines)
            # print
            max_s,min_s = max(slope_l),min(slope_l)
            max_a,min_a = max(angle_l),min(angle_l)

            # normalize values
            hessen_lines = [((max_s-s)/(max_s-min_s),(max_a-a)/(max_a-min_a)) for s,a in hessen_lines]
            # print hessen_lines

            tree = spatial.KDTree(hessen_lines)

            to_merge = []
            will_be_merged = set()

            for l_index in range(len(hessen_lines)-1,-1,-1):
                for l2_index in tree.query_ball_point(hessen_lines[l_index],0.15):
                    if l2_index > l_index:
                        t_lines = clusters[l_index][0][:]
                        t_lines.extend(clusters[l2_index][0])

                        aligned_text = self.__get_aggregation_lines__(t_lines)
                        accuracy = self.__agreement__(aligned_text)
                        if min(accuracy) >= 0.5:
                            will_be_merged.add(l_index)
                            will_be_merged.add(l2_index)

                            # make sure that there are not any overlapping users
                            users_1 = zip(*clusters[l_index][1])[1]
                            users_2 = zip(*clusters[l2_index][1])[1]

                            if [u for u in users_1 if u in users_2] != []:
                                continue

                            # is merge "relevant" to any other?
                            relevant = False
                            for m_index,m in enumerate(to_merge):
                                if (l_index in m) or (l2_index in m):
                                    relevant = True
                                    m.add(l_index)
                                    m.add(l2_index)
                                    break

                            if not relevant:
                                to_merge.append(set([l_index,l2_index]))

            # might be a better way to do this but will mulitple popping from list, safer
            # to work with a copy
            new_clusters = []

            for cluster_index in range(len(clusters)):
                if cluster_index not in will_be_merged:
                    new_clusters.append(clusters[cluster_index])
            for merged_clusters in to_merge:
                t_cluster = [[],[]]
                for cluster_index in merged_clusters:
                    t_cluster[0].extend(clusters[cluster_index][0])
                    t_cluster[1].extend(clusters[cluster_index][1])
                new_clusters.append(t_cluster[:])

            # print clusters
            clusters = new_clusters

        # and now, finally, the actual text clustering
        cluster_centers = []
        cluster_pts = []
        cluster_users = []

        cluster_members = []

        for lines,pts_and_users in clusters:
            pts,users = zip(*pts_and_users)
            x1_values,x2_values,y1_values,y2_values = zip(*pts)

            # todo - handle when some of the coordinate values are not numbers -
            # this corresponds to when there are multiple text segments from the same user
            x1 = np.median(x1_values)
            x2 = np.median(x2_values)
            y1 = np.median(y1_values)
            y2 = np.median(y2_values)

            aligned_text = self.__get_aggregation_lines__(lines)
            aggregate_text = ""
            for char_index in range(len(aligned_text[0])):
                char_set = set(text[char_index] for text in aligned_text)
                # get the percentage of votes for each character at this position
                char_vote = {c:sum([1 for text in aligned_text if text[char_index] == c])/float(len(aligned_text)) for c in char_set}
                most_likely_char,vote_percentage = max(char_vote.items(),key=lambda x:x[1])

                if vote_percentage > 0.75:
                    aggregate_text += most_likely_char
                else:
                    aggregate_text += "-"

            aggregate_text = re.sub(r'@'," ",aggregate_text)

            cluster_centers.append((x1,x2,y1,y2,aggregate_text))
            cluster_pts.append(zip(pts,lines))
            cluster_users.append(users)

            # try to remove all special characters
            temp_text = []
            for text in aligned_text:
                text = re.sub("@"," ",text)
                temp_text.append(text)

            cluster_members.append(temp_text)

        # results.append({"users":merged_users,"cluster members":merged_points,"tools":merged_tools,"num users":num_users})

        results = []
        for center,pts,users,lines in zip(cluster_centers,cluster_pts,cluster_users,cluster_members):
            results.append({"center":center,"cluster members":lines,"tools":[],"num users":len(users)})

        # return (cluster_centers,cluster_pts,cluster_users),0
        return results,0


class SimplifiedTate(transcription.Tate):
    def __init__(self):
        transcription.Tate.__init__(self)

        reduction_algs = {"text":transcription.text_line_reduction}
        self.__set_clustering_algs__({"text":SimplifiedTextCluster},reduction_algs)

        # self.old_time = datetime.datetime(2015,8,27)
        self.starting_date = datetime.datetime(2015,8,27)

        try:
            self.old_time = pickle.load(open("/tmp/"+str(self.project_id)+".time","rb"))
        except:
            self.old_time = datetime.datetime(2015,8,27)

if __name__ == "__main__":
    with SimplifiedTate() as project:
        # project.__migrate__()
        project.__aggregate__(workflows=[121])
        # print project.__get_retired_subjects__(121)