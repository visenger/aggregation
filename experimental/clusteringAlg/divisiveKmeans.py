__author__ = 'ggdhines'
from sklearn.cluster import KMeans
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.cbook as cbook
import six
from matplotlib import colors
import math

class DivisiveKmeans:
    def __init__(self, min_samples):
        self.min_samples = min_samples

    def __fix__(self,centers,clusters,users_per_cluster,threshold,f_name=None):
        #look for abnormally close clusters with only one or zero users in common
        #zero is possible as a result of how k-means splits points
        #users per cluster must in the same order as the points per cluster
        while True:
            #compare every pair of clusters - returns only those clusters with 0 or 1 users in common
            #within the threshold
            relations = self.calc_relations(centers,users_per_cluster,threshold)
            if relations == []:
                break

            #look at the closest pair
            overlap = relations[0][1]
            distance = relations[0][0]
            c1_index = relations[0][2]
            c2_index = relations[0][3]

            #make sure to pop in the right order so else the indices will get messed up
            if c2_index > c1_index:
                cluster_2 = clusters.pop(c2_index)
                cluster_1 = clusters.pop(c1_index)

                cent_2 = centers.pop(c2_index)
                cent_1 = centers.pop(c1_index)

                users_2 = users_per_cluster.pop(c2_index)
                users_1 = users_per_cluster.pop(c1_index)

            else:
                cluster_1 = clusters.pop(c1_index)
                cluster_2 = clusters.pop(c2_index)

                cent_1 = centers.pop(c1_index)
                cent_2 = centers.pop(c2_index)

                users_1 = users_per_cluster.pop(c1_index)
                users_2 = users_per_cluster.pop(c2_index)

            #the distance < threshold check may be redundant - since calc_relations can also check
            #but doesn't hurt
            if (overlap != []) and (distance < threshold):
                assert(len(overlap) == 1)
                overlap_user = overlap[0]
                #the point in each cluster which corresponds to the overlapping user
                p1 = cluster_1.pop(users_1.index(overlap_user))
                #double check that there no other equaivalent points in the array
                #shouldn't happen - unless by really bad luck
                assert sum([1 for p in cluster_1 if (p == p1)]) == 0

                p2 = cluster_2.pop(users_2.index(overlap_user))
                #double check that there no other equaivalent points in the array
                #shouldn't happen - unless by really bad luck
                assert sum([1 for p in cluster_1 if (p == p2)]) == 0

                #since we have removed the points, we now remove the users themselves
                users_1.remove(overlap_user)
                users_2.remove(overlap_user)

                #now merge
                #for now, only deal with 2D points - which should always be the case
                assert len(p1) == 2
                avg_pt = ((p1[0]+p2[0])/2., (p1[1]+p2[1])/2.)
                joint_cluster = cluster_1[:]
                joint_cluster.extend(cluster_2)
                joint_cluster.append(avg_pt)

                joint_users = users_1[:]
                joint_users.extend(users_2)
                joint_users.append(overlap_user)

                #recalculate the center
                X,Y = zip(*joint_cluster)
                center = (np.mean(X),np.mean(Y))

                #add this new merged cluster back
                centers.append(center)
                clusters.append(joint_cluster)
                users_per_cluster.append(joint_users)

            else:
                assert overlap == []
                #we have no nearby clusters with no common users - should be easy to merge

                joint_cluster = cluster_1[:]
                joint_cluster.extend(cluster_2)

                joint_users = users_1[:]
                joint_users.extend(users_2)

                #recalculate the center
                X,Y = zip(*joint_cluster)
                center = (np.mean(X),np.mean(Y))

                #add this new merged cluster back
                centers.append(center)
                clusters.append(joint_cluster)
                users_per_cluster.append(joint_users)

        return centers,clusters,users_per_cluster

    def calc_relations(self,centers,users_per_cluster,threshold):
        relations = []
        for c1_index in range(len(centers)):
            for c2_index in range(c1_index+1,len(centers)):
                c1 = centers[c1_index]
                c2 = centers[c2_index]

                u1 = users_per_cluster[c1_index]
                u2 = users_per_cluster[c2_index]

                dist = math.sqrt((c1[0]-c2[0])**2+(c1[1]-c2[1])**2)

                overlap = [u for u in u1 if u in u2]
                #print (len(overlap),dist)

                #print (len(overlap),dist)
                if (len(overlap) <= 1) and (dist <= threshold):
                    relations.append((dist,overlap,c1_index,c2_index))

        relations.sort(key= lambda x:x[0])
        relations.sort(key= lambda x:len(x[1]))

        return relations

    # def fit(self, markings,user_ids,jpeg_file=None,debug=False):
    #     clusters_to_go = []
    #     clusters_to_go.append((markings,user_ids,1))
    #
    #     print user_ids
    #
    #     end_clusters = []
    #     cluster_centers = []
    #
    #     while True:
    #         #if we have run out of clusters to process, break (hopefully done :) )
    #         if clusters_to_go == []:
    #             break
    #         m_,u_,num_clusters = clusters_to_go.pop(0)
    #
    #         #increment by 1
    #         kmeans = KMeans(init='k-means++', n_clusters=num_clusters+1, n_init=10).fit(markings)
    #
    #         labels = kmeans.labels_
    #         unique_labels = set(labels)
    #         for k in unique_labels:
    #             users = [ip for index,ip in enumerate(u_) if labels[index] == k]
    #             points = [pt for index,pt in enumerate(m_) if labels[index] == k]
    #
    #             #if the cluster does not have the minimum number of points, just skip it
    #             if len(points) < self.min_samples:
    #                 continue
    #
    #             #we have found a "clean" - final - cluster
    #             if len(set(users)) == len(users):
    #                 end_clusters.append(points)
    #                 X,Y = zip(*points)
    #                 cluster_centers.append((np.mean(X),np.mean(Y)))
    #             else:
    #                 clusters_to_go.append((points,users,num_clusters+1))
    #
    #
    #
    #
    #     if debug:
    #         return cluster_centers, end_clusters,total_noise2
    #     else:
    #         return cluster_centers

    def fit(self, markings,user_ids,jpeg_file=None,debug=False):
        #check to see if we need to split at all, i.e. there might only be one animal in total

        total = 0

        if len(user_ids) == len(list(set(user_ids))):
            #do these points meet the minimum threshold value?
            if len(markings) >= self.min_samples:
                X,Y = zip(*markings)
                cluster_centers = [(np.mean(X),np.mean(Y)), ]
                end_clusters = [markings,]
                if debug:
                    return cluster_centers, end_clusters,user_ids
                else:
                    return cluster_centers
            else:
                if debug:
                    return [], [],[]
                else:
                    return []

        clusters_to_go = []
        clusters_to_go.append((markings,user_ids,1))

        end_clusters = []
        cluster_centers = []
        end_users = []

        colors_ = list(six.iteritems(colors.cnames))

        while True:
            #if we have run out of clusters to process, break (hopefully done :) )
            if clusters_to_go == []:
                break
            m_,u_,num_clusters = clusters_to_go.pop(-1)

            if jpeg_file is not None:
                image_file = cbook.get_sample_data(jpeg_file)
                image = plt.imread(image_file)
                fig, ax = plt.subplots()
                im = ax.imshow(image)

                X,Y = zip(*markings)
                #X = [1.875 *x for x in X]
                #Y = [1.875 *y for y in Y]
                plt.plot(X,Y,'.',color="blue")

                X,Y = zip(*m_)
                #X = [1.875 *x for x in X]
                #Y = [1.875 *y for y in Y]
                plt.plot(X,Y,'.',color="red")
                plt.show()

            #increment by 1
            while True:
                num_clusters += 1
                try:
                    kmeans = KMeans(init='k-means++', n_clusters=num_clusters, n_init=10).fit(m_)
                    total += 1
                except ValueError:
                    #all of these are noise - since we can't actually separate them
                    break

                labels = kmeans.labels_
                unique_labels = set(labels)
                temp_end_clusters = []
                temp_clusters_to_go = []
                temp_cluster_centers = []
                temp_users = []

                for k in unique_labels:
                    users = [ip for index,ip in enumerate(u_) if labels[index] == k]
                    points = [pt for index,pt in enumerate(m_) if labels[index] == k]
                    assert(users != [])

                    #if the cluster does not have the minimum number of points, just skip it
                    if len(points) < self.min_samples:
                        continue

                    #we have found a "clean" - final - cluster
                    if len(set(users)) == len(users):
                        temp_end_clusters.append(points)
                        X,Y = zip(*points)
                        temp_cluster_centers.append((np.mean(X),np.mean(Y)))
                        temp_users.append(users)
                    else:
                        temp_clusters_to_go.append((points,users,1))

                if temp_end_clusters != []:
                    end_clusters.extend(temp_end_clusters)
                    cluster_centers.extend(temp_cluster_centers)
                    clusters_to_go.extend(temp_clusters_to_go)
                    end_users.extend(temp_users)
                    break

        #print total

        for c in end_clusters:
            assert(len(c) >= self.min_samples)

        if True:
            return cluster_centers, end_clusters,end_users
        else:
            return cluster_centers