#!/usr/bin/env python
# import matplotlib
# matplotlib.use('WXAgg')
from aggregation_api import AggregationAPI
import helper_functions
from classification import Classification
import clustering
import numpy as np
import re
import unicodedata
import os
import requests
import rollbar
import json
import sys
import yaml
from blob_clustering import BlobClustering
import boto3
import pickle
import getopt
from dateutil import parser
import botocore
import matplotlib.pyplot as plt
import math
import tempfile
import networkx
import botocore.session
import tarfile
import datetime
import cassandra
from text_clustering import TextClustering

__author__ = 'greg'

if os.path.exists("/home/ggdhines"):
    base_directory = "/home/ggdhines"
else:
    base_directory = "/home/greg"


def longest_common_substring(s1, s2):
    """
    taken from https://en.wikibooks.org/wiki/Algorithm_Implementation/Strings/Longest_common_substring#Python2
    :param s1:
    :param s2:
    :return:
    """
    m = [[0] * (1 + len(s2)) for i in xrange(1 + len(s1))]
    longest, x_longest = 0, 0
    for x in xrange(1, 1 + len(s1)):
        for y in xrange(1, 1 + len(s2)):
            if s1[x - 1] == s2[y - 1]:
                m[x][y] = m[x - 1][y - 1] + 1
                if m[x][y] > longest:
                    longest = m[x][y]
                    x_longest = x
            else:
                m[x][y] = 0
    return s1[x_longest - longest: x_longest]


class FolgerClustering(TextClustering):
    def __init__(self,shape,project,param_dict):
        TextClustering.__init__(self,shape,project,param_dict)

        self.folger_safe_tags = dict()

        # for folger the tags in the transcriptions are not actually the tags that folger wants
        for key,tag in self.tags.items():
            self.folger_safe_tags[key] = tag.replace("sw-","")

    def __accuracy__(self,s):
        assert isinstance(s,str)
        assert len(s) > 0
        return sum([1 for c in s if c != "-"])/float(len(s))

    def __reset_tags__(self,text):
        """
        with text, we will have tags represented by a single character (with ord() > 128 to indicate
        that something is special) Convert these back to the full text representation
        also take care of folger specific stuff right
        :param text:
        :return:
        """
        assert isinstance(text,str)

        # reverse_map = {v: k for k, v in self.tags.items()}
        # also go with something different for "not sure"
        # this matter when the function is called on the aggregate text
        # reverse_map[200] = chr(27)
        # and for gaps inserted by MAFFT
        # reverse_map[201] = chr(24)

        ret_text = ""

        for c in text:
            if ord(c) > 128:
                ret_text += self.folger_safe_tags[ord(c)]
            else:
                ret_text += c

        assert isinstance(text,str)
        return ret_text

    def __find_completed_components__(self,aligned_text,coordinates):
        """
        go through the aggregated text looking for subsets where at least 3 people have transcribed everything
        :param aligned_text:
        :param coordinates:
        :return:
        """
        completed_indices = []
        for char_index in range(len(aligned_text[0])):
            char_set = set(text[char_index] for text in aligned_text)
            # 25 means that user hasn't transcribed this part of the line - NOT an inserted gap
            char_vote = {c:sum([1 for text in aligned_text if text[char_index] == c]) for c in char_set if ord(c) != 25}

            if sum(char_vote.values()) >= 3:
                completed_indices.append(char_index)

        completed_starting_point = {}
        completed_ending_point = {}

        # transcription_range = {}

        # find consecutive blocks
        if completed_indices != []:
            blocks = [[completed_indices[0]],]
            for i,char_index in list(enumerate(completed_indices))[1:]:
                if completed_indices[i-1] != (char_index-1):
                    blocks[-1].append(completed_indices[i-1])
                    blocks.append([char_index])

            blocks[-1].append(completed_indices[-1])

            # technically we can have multiple transcriptions from the same user so
            # instead of user_index, I'll use transcription_index
            # also, technically the same user could give transcribe the same piece of text twice (or more)
            # and include those transcriptions in different annotations. Going to assume that doesn't happen
            for transcription_index,(text,coord) in enumerate(zip(aligned_text,coordinates)):
                x1,x2,y1,y2 = coord
                non_space_characters = [i for (i,c) in enumerate(text) if ord(c) != 25]

                first_char = min(non_space_characters)
                last_char = max(non_space_characters)

                # transcription_range[transcription_index] = (first_char,last_char)

                # look for transcriptions which exactly match up with the completed segment
                # match on either starting OR ending point matching up
                # we'll use these transcriptions to determine where to place the red dots
                # telling people to no longer transcribe that text
                # such transcriptions may not exist - in which case we cannot really do anything
                for b in blocks:
                    # does the start of the transcription match up with the start of the completed segment
                    if b[0] == first_char:
                        if (first_char,last_char) in completed_starting_point:
                            completed_starting_point[(first_char,last_char)].append((x1,y1))
                        else:
                            completed_starting_point[(first_char,last_char)] = [(x1,y1)]

                    # does the end of the transcription match up with the end of the completed segment?
                    if b[1] == last_char:
                        if (first_char,last_char) in completed_ending_point:
                            completed_ending_point[(first_char,last_char)].append((x2,y2))
                        else:
                            completed_ending_point[(first_char,last_char)] = [(x2,y2)]

        return completed_starting_point,completed_ending_point

    def __create_clusters__(self,(completed_starting_point,completed_ending_point),aggregated_text,transcription_range,markings):
        """
        the aggregated text, split up into completed components and make a result (aggregate) cluster for each
        of those components
        :param aggregated_text:
        :param transcription_range: where (relative to the aggregate text) each transcription string starts and stops
        useful for differentiating between gap markers before or after the text and gaps inside the text
        :param markings: the original markings - without the tags tokenized
        :return:
        """
        clusters = []

        # go through every segment that is considered done
        for (lb,ub) in completed_starting_point:
            # not sure how likely this is to happen, but just to be sure
            # make sure that we have both a starting and ending point
            if (lb,ub) not in completed_ending_point:
                continue

            new_cluster = {}

            X1,Y1 = zip(*completed_starting_point[(lb,ub)])
            X2,Y2 = zip(*completed_ending_point[(lb,ub)])

            x1 = np.median(X1)
            x2 = np.median(X2)
            y1 = np.median(Y1)
            y2 = np.median(Y2)

            completed_text = self.__reset_tags__(aggregated_text[lb:ub+1])
            new_cluster["center"] = (x1,x2,y1,y2,completed_text)

            new_cluster["cluster members"] = []

            # which transcriptions contributed to this piece of text being considered done?
            # note that we are not looking for (lb_j,ub_j) to completely contain the completed segment
            # (although I think most of the time that will be the case) - any overlap will count
            # this will be needed if people want to go back and look at the raw data
            for j,(lb_j,ub_j) in enumerate(transcription_range):

                if (lb_j <= lb <= ub_j) or (lb_j <= ub <= ub_j):
                    (x1,x2,y1,y2,transcription) = markings[j]
                    new_marking = (x1,x2,y1,y2,self.__reset_tags__(transcription))
                    new_cluster["cluster members"].append(new_marking)

            new_cluster["num users"] = len(new_cluster["cluster members"])

            clusters.append(new_cluster)

        return clusters

    def __merge_aligned_text__(self,aligned_text):
        """
        once we have aligned the text using MAFFT, use this function to actually decide on an aggregate
        result - will also return the % of agreement
        and the percentage of how many characters for each transcription agree with the agree
        handles special tags just fine - and assumes that we have dealt with capitalization already
        """
        aggregate_text = ""
        num_agreed = 0

        # will keep track of the percentage of characters from each transcription which agree
        # with the aggregate
        agreement_per_user = [0 for i in aligned_text]

        # self.stats["line_length"].append(len(aligned_text[0]))

        vote_history = []

        uncompleted_characters = 0

        for char_index in range(len(aligned_text[0])):
            # get all the possible characters
            # todo - we can reduce this down to having to loop over each character once
            # todo - handle case (lower case vs. upper case) better
            char_set = set(text[char_index] for text in aligned_text)
            # get the percentage of votes for each character at this position
            char_vote = {c:sum([1 for text in aligned_text if text[char_index] == c]) for c in char_set if ord(c) != 25}
            vote_history.append(char_vote)

            # get the most common character (also the most likely to be the correct one) and the percentage of users
            # who "voted" for it

            # have at least 3 people transcribed this character?
            if sum(char_vote.values()) >= 3:
                self.stats["characters"] += 1

                most_likely_char,max_votes = max(char_vote.items(),key=lambda x:x[1])
                vote_percentage = max_votes/float(sum(char_vote.values()))

                # is there general agreement about what this character is?
                if vote_percentage > 0.5:
                    num_agreed += 1
                    aggregate_text += most_likely_char

                # check for special cases with double spaces or only differences about capitalization
                elif len(char_vote) == 2:
                    sorted_keys = [c for c in sorted(char_vote.keys())]
                    # this case => at least one person transcribed " " and at least one other
                    # person transcribed 24 (i.e. nothing) - so it might be that the first person accidentally
                    # gave " " which we'll assume means a double space so skip
                    if (ord(sorted_keys[0]) == 24) and (sorted_keys[1] == " "):
                        # but only skip it if at least two person gave 24
                        raw_counts = {c:sum([1 for text in aligned_text if text[char_index] == c]) for c in char_set}
                        if raw_counts[chr(24)] >= 2:
                            aggregate_text += chr(24)
                        else:
                            # 27 => disagreement
                            aggregate_text += chr(27)
                            self.stats["errors"] += 1

                    # capitalization issues? only two different transcriptions given
                    # one the lower case version of the other
                    elif sorted_keys[0].lower() == sorted_keys[1].lower():
                        aggregate_text += sorted_keys[0].upper()
                    # otherwise two different transcriptions but doesn't meet either of the special cases
                    else:
                        aggregate_text += chr(27)
                        self.stats["errors"] += 1
                else:
                    # chr(27) => disagreement
                    aggregate_text += chr(27)
                    self.stats["errors"] += 1
            else:
                # not enough people have transcribed this character
                aggregate_text += chr(26)
                uncompleted_characters += 1

                # for a in aligned_text:
                #     print a + "|"
                # assert False

        if uncompleted_characters == 0:
            self.stats["retired lines"] += 1
        assert len(aggregate_text) > 0

        try:
            percent_consensus = num_agreed/float(len([a for a in aggregate_text if ord(a) != 26]))
            percent_complete = len([a for a in aggregate_text if ord(a) != 26])/float(len(aggregate_text))
        except ZeroDivisionError:
            percent_complete = 0
            percent_consensus = -1

        return aggregate_text

    def __add_alignment_spaces__(self,aligned_text_list,tokenized_text):
        """
        take the text representation where we still have upper case and lower case letters
        plus special characters for tags (so definitely not the input for MAFFT) and add in whatever
        alignment characters are needed (say char(201)) so that the first text representations are all
        aligned
        fasta is the format the MAFFT reads in from - so non_fasta_text contains non-alpha-numeric ascii chars
        pts_and_users is used to match text in aligned text with non_fasta_text
        """

        aligned_nf_text_list = []
        transcription_range = []
        for text,nf_text in zip(aligned_text_list,tokenized_text):
            aligned_nf_text = ""

            # added spaces before or after all of the text need to be treated differently
            non_space_characters = [i for (i,c) in enumerate(text) if c != "-"]
            try:
                first_char = min(non_space_characters)
            except ValueError:
                print text
                print nf_text
                print aligned_text_list
                raise
            last_char = max(non_space_characters)

            transcription_range.append((first_char,last_char))

            i = 0
            for j,c in enumerate(text):
                if c == "-":
                    if first_char <= j <= last_char:
                        # this is a gap where the person may have missed something
                        aligned_nf_text += chr(24)
                    else:
                        # this corresponds to before or after the person started transcribing
                        aligned_nf_text += chr(25)
                else:
                    aligned_nf_text += nf_text[i]
                    i += 1
            aligned_nf_text_list.append(aligned_nf_text)

        return aligned_nf_text_list,transcription_range

    def __filter_markings__(self,markings):
        """
        filter out any markings which are not horizontal or are empty after removing bad characters
        :return:
        """
        # todo - generalize for non-horizontal markings
        filtered_markings = []

        for m_i,(x1,x2,y1,y2,t) in enumerate(markings):
            # skip empty strings - but make sure when checking to first remove tags that shouldn't
            # be there in the first place
            # set_tags removes some tags (such as <br>) which we don't want at all
            # so if a transcription is just "<br>" we should skip it
            processed_text = self.__set_tags__(t.encode('ascii','ignore'))
            if processed_text == "":
                continue

            # check the angle
            try:
                tan_theta = math.fabs(y1-y2)/math.fabs(x1-x2)
                theta = math.atan(tan_theta)
            except ZeroDivisionError:
                theta = math.pi/2.

            if math.fabs(theta) > 0.1:
                # removed_count += 1
                continue

            filtered_markings.append((x1,x2,y1,y2,processed_text))

        return filtered_markings

    def __find_connected_transcriptions__(self,markings):
        """
        cluster transcriptions such that each cluster corresponds to the same line of text
        do this with connected components in a graph - hence the function name
        :return a list of lists - each "sub" list is list of indices for markings in that transcription:
        """
        G = networkx.Graph()
        G.add_nodes_from(range(len(markings)))

         # now look for the overlapping parts
        # examine every pair - note that distance from A to B does not necessarily equal
        # the distance from B to A - so order matters
        for m_i,(x1,x2,y1,y2,t) in enumerate(markings):
            for m_i2,(x1_,x2_,y1_,y2_,_) in enumerate(markings):
                # assuming two purely horizontal lines - consider the following example
                # x1 ----------- x2
                #     x1_----x2_
                # here the distance from x1 to the second line is the distance from x1 to x1_
                # but the distance from x1_ to the first line, is purely the vertical distance
                # since ignoring vertical distance, the second line is a subset of the first
                # so we can be pretty sure that the second line transcribes a subset of the first
                if m_i == m_i2:
                    continue

                # since we threw out all non-horizontal lines (within a certain degree of error)
                # the slope doesn't really matter - but doesn't hurt and should help when we generalize to
                # non-horizontal lines
                slope = (y2_-y1_)/float(x2_-x1_)
                inter = y2_ - slope*x2_

                # see https://en.wikipedia.org/wiki/Distance_from_a_point_to_a_line
                # for explanation of the below code
                a = -slope
                b = 1
                c = -inter
                dist_1 = math.fabs(a*x1+b*y1+c)/math.sqrt(a**2+b**2)
                x = (b*(b*x1-a*y1)-a*c)/float(a**2+b**2)

                # if x is outside of the line segment in either direction - recalculate the distance as explained
                # above
                # todo - we could probably merge this if statement with the next one
                if x < x1_:
                    x = x1_
                    y = y1_
                    dist_1 = math.sqrt((x-x1)**2+(y-y1)**2)
                elif x > x2_:
                    x = x2_
                    y = y2_
                    dist_1 = math.sqrt((x-x1)**2+(y-y1)**2)

                # repeat for x2,y2
                dist_2 = math.fabs(a*x2+b*y2+c)/math.sqrt(a**2+b**2)
                x = (b*(b*x2-a*y2)-a*c)/float(a**2+b**2)

                if x < x1_:
                    x = x1_
                    y = y1_
                    dist_2 = math.sqrt((x-x2)**2+(y-y2)**2)
                elif x > x2_:
                    x = x2_
                    y = y2_
                    dist_2 = math.sqrt((x-x2)**2+(y-y2)**2)

                # if the average distance is less than 10 (an arbitrary threshold) then assume there is an overlap
                # that is - these two transcriptions are transcribing at least some of the same text
                if (dist_1+dist_2)/2. < 10:
                    G.add_path([m_i,m_i2])

        # look for connect components - i.e. sets of overlapping transcriptions
        clusters = [c for c in list(networkx.connected_components(G)) if len(c) > 1]

        return clusters

    def __cluster__(self,markings,user_ids,tools,reduced_markings,image_dimensions,subject_id,recursive=False):
        """
        cluster the line segments transcriptions together - look for overlaping parts
        note that overlaping is not transitive - if A overlaps B and B overlap C, it does not follow
        that A overlaps C. So we'll use some graph theory instead to search for
        """

        # image is kept mainly just for debugging
        image = None

        # remove any non-horizontal markings or empty transcriptions
        # also a good place to tokenize tags
        filtered_markings = self.__filter_markings__(markings)

        # cluster the filtered components
        connected_components = self.__find_connected_transcriptions__(filtered_markings)

        clusters = []

        for c in connected_components:
            if len(c) <= 2:
                continue

            # extract the starting/ending x-y coordinates for each transcription in the cluster
            coordinates = [filtered_markings[i][:-1] for i in c]
            # as well as the text - at the same time deal with tags (make them all 1 character long)
            # and other special characters that MAFFT can't deal with
            tokenized_text = [filtered_markings[i][-1] for i in c]

            # tokenized_text has each tag (several characters) represented by just one (non-standard ascii) character
            # aka a token
            # mafft_safe_text converts all upper case letters to lower case
            # and uses upper case letters to represent things that MAFFT can't deal with (e.g. tag tokens)
            mafft_safe_text = [self.__set_special_characters__(t) for t in tokenized_text]

            # align based on the lower case items
            aligned_mafft_text = self.__line_alignment__(mafft_safe_text)
            # use that alignment to align the tokenized text items (which is isomorphic to the original text)
            # also a good place where to which exactly what part of the line each transcription transcribed
            # since there is a difference for gaps inserted before or after the transcription (which reall aren't
            # gaps at all) and gaps inside the transcription
            aligned_text,transcription_range = self.__add_alignment_spaces__(aligned_mafft_text,tokenized_text)

            # aggregate the individual pieces of text together
            aggregate_text = self.__merge_aligned_text__(aligned_text)
            # find where the text has been transcribed by at least 3 people
            completed_components = self.__find_completed_components__(aligned_text,coordinates)
            # (completed_starting_point,completed_ending_point),aggregated_text,transcription_range,markings
            markings_in_cluster = [filtered_markings[i] for i in c]
            clusters.extend(self.__create_clusters__(completed_components,aggregate_text,transcription_range,markings_in_cluster))

        print "number of completed components: " + str(len(clusters))
        return clusters,0