# -*- coding: utf8 -*- 
from __future__ import division, print_function

import numpy as np
from collections import OrderedDict
from itertools import permutations


class Triangulation(object):
    """
    Constrained delaunay implementation based on 

    Domiter, V. and Žalik, B.
    Sweep‐line algorithm for constrained Delaunay triangulation

    (this implementation is not complete)
    
    Parameters:
    pts : array((N, 2), dtype=float)
    edges : array((N, 2), dtype=int)
    
    Notes:
    
    The pts and edges arrays may be modified!
    """
    
    def __init__(self, pts, edges):
        self.pts = pts[:, :2].astype(np.float32)
        self.edges = edges
        
        # described in initialize()
        self.front = [0, 2, 1]
        self.tris = []
        self.edges_lookup = {}
        
    def normalize(self):
        # Clean up data   (not discussed in original publication)
        
        # (i) Split intersecting edges. Every edge that intersects another 
        #     edge or point is split. This extends self.pts and self.edges.
        self.split_intersecting_edges()
        
        # (ii) Merge identical points. If any two points are found to be equal,
        #      the second is removed and the edge table is updated accordingly. 
        self.merge_duplicate_points()

        # (iii) Remove duplicate edges
        # TODO

    def initialize(self):
        self.normalize()
        ## Initialization (sec. 3.3)

        # sort points by y, then x
        flat_shape = self.pts.shape[0] * self.pts.shape[1]
        pts = self.pts.reshape(flat_shape).view([('x', np.float32), 
                                                 ('y', np.float32)])
        order = np.argsort(pts, order=('y', 'x'))
        pts = pts[order]
        # update edges to match new point order
        invorder = np.argsort(order)
        self.edges = invorder[self.edges]
        self.pts = pts.view(np.float32).reshape(len(pts), 2)

        # make artificial points P-1 and P-2
        xmax = self.pts[:,0].max()
        xmin = self.pts[:,0].min()
        ymax = self.pts[:,1].max()
        ymin = self.pts[:,1].min()
        xa = (xmax-xmin) * 0.3
        ya = (ymax-ymin) * 0.3
        p1 = (xmin - xa, ymin - ya)
        p2 = (xmax + xa, ymin - ya)

        # prepend artificial points to point list
        newpts = np.empty((self.pts.shape[0]+2, 2), dtype=float)
        newpts[0] = p1
        newpts[1] = p2
        newpts[2:] = self.pts
        self.pts = newpts
        self.edges += 2

        # find topmost point in each edge
        self.tops = self.edges.max(axis=1)
        self.bottoms = self.edges.min(axis=1)

        # inintialize sweep front
        # values in this list are indexes into self.pts
        self.front = [0, 2, 1]
        
        # empty triangle list. 
        # This will contain [(a, b, c), ...] where a,b,c are indexes into 
        # self.pts
        self.tris = []

        # For each triangle, maps (a, b): c
        # This is used to look up the thrid point in a triangle, given any edge. 
        # Since each edge has two triangles, they are independently stored as 
        # (a, b): c and (b, a): d
        self.edges_lookup = {}


    def triangulate(self):
        self.initialize()
        pts = self.pts
        edges = self.edges
        front = self.front
        
        ## Begin sweep (sec. 3.4)
        for i in range(3, pts.shape[0]):
            pi = pts[i]
            debug("========== New point %d: %s ==========" % (i, pi))
            
            # First, triangulate from front to new point
            # This applies to both "point events" (3.4.1) and "edge events" (3.4.2).

            # get index along front that intersects pts[i]
            l = 0
            while pts[front[l+1], 0] <= pi[0]:
                l += 1
            pl = pts[front[l]]
            pr = pts[front[l+1]]
            
            # "(i) middle case"
            if pi[0] > pl[0]:  
                debug("  mid case")
                # Add a single triangle connecting pi,pl,pr
                self.add_tri(front[l], front[l+1], i)
                front.insert(l+1, i)
                front_index = l+1
            # "(ii) left case"
            else:
                debug("  left case")
                ps = pts[l-1]
                # Add triangles connecting pi,pl,ps and pi,pl,pr
                self.add_tri(front[l], front[l+1], i)
                self.add_tri(front[l-1], front[l], i)
                front[l] = i
                front_index = l
            
            debug(front)
                
            # Continue adding triangles to smooth out front
            # (heuristics shown in figs. 9, 10)
            debug("Smoothing front...")
            for direction in -1, 1:
                while True:
                    # Find point connected to pi
                    ind0 = front.index(i)
                    ind1 = ind0 + direction
                    ind2 = ind1 + direction
                    if ind2 < 0 or ind2 >= len(front):
                        break
                    
                    # measure angle made with front
                    p1 = pts[front[ind1]]
                    p2 = pts[front[ind2]]
                    angle = np.arccos(self.cosine(pi, p1, p2))
                    
                    # if angle is < pi/2, make new triangle
                    debug("Smooth angle:", pi, p1, p2, angle)
                    if angle > np.pi/2. or np.isnan(angle):
                        break
                    
                    assert (i != front[ind1] and 
                            front[ind1] != front[ind2] and 
                            front[ind2] != i)
                    self.add_tri(i, front[ind1], front[ind2], source='smooth1')
                    front.pop(ind1)
            debug("Finished smoothing front.")
            
            # "edge event" (sec. 3.4.2)
            # remove any triangles cut by completed edges and re-fill the holes.
            if i in self.tops:  
                for j in self.bottoms[self.tops == i]:
                    self.edge_event(i, j, front_index)  # Make sure edge (j, i) is present in mesh
                    front = self.front # because edge event may have created a new front list
                
                
                
                ## Locate the other endpoint
                #found = False
                #for e in edges:
                    #if i in e:
                        #found = True
                        #endpoint = e[0] if (e[1] == i) else e[1]
                        #break
                #if not found:
                    #debug("    Other end point not located; continuing.")
                    #continue
                
                #debug("    Locate first intersected triangle")
                ## (i) locate intersected triangles
                #"""
                #If the first intersected triangle contains the top point,
                #then start traversal there. Also, if an intersected triangle
                #contains the top point, then it has to be the first intersected
                #triangle.
                #"""
                ##debug("  edges lookup:")
                ##debug(edges_lookup)
                
                #vals = edges_lookup.values()
                #edge_intersects = False
                #for value in vals:
                    #if value == i:          # loop over all triangles containing Pi
                        #current_side = edges_lookup.keys()[vals.index(i)]
                        ## todo: might be sped up by using cross product as described in fig. 11
                        #if intersects(current_side, e):
                            #edge_intersects = True
                            #break

                ## (ii) remove intersected triangles
                #upper_polygon = []
                #lower_polygon = []

                #if not edge_intersects:
                    ## find the closest intersection to point
                    #h_max = 0
                    #closest_edge = None
                    #for edge in edges_lookup.keys():
                        #h = intersection(edge, e)
                        #if h >= 0 and h < 1 and h > h_max:
                            #h_max = h
                            #closest_edge = edge
                    #if not closest_edge:
                        ## the edge does not intersect any lines
                        ## triangulate the points on the front lying between the edge
                        #start = front.index(i)
                        #end = front.index(endpoint)
                        #upper_polygon.append(i)
                        #lower_polygon.append(i)
                        #c = -1 if (start > end) else 1
                        #for k in range(start+c, end, c):
                            #if orientation((i, endpoint), front[k]) > 0:
                                #upper_polygon.append(front[k])
                            #else:
                                #lower_polygon.append(front[k])
                                #front.pop(k)

                #else:
                    #remove_tri(*(current_side+(i,)))
                    #upper_polygon.append(i)
                    #lower_polygon.append(i)
                    #if orientation((i, endpoint), current_side[0]) > 0:
                        #upper_polygon.append(current_side[0])
                        #lower_polygon.append(current_side[1])
                    #else:
                        #upper_polygon.append(current_side[1])
                        #lower_polygon.append(current_side[0])
                    ## now traverse and remove all intersecting triangles
                    #try:
                        #other_vertex = edges_lookup[current_side[::-1]]
                        #remove_tri(*(current_side+(other_vertex, )))
                    #except KeyError:
                        #other_vertex = endpoint
                    #while (other_vertex != endpoint):
                        ## now the edge intersects one of the triangles on either sides
                        ## of current triangle, we find which one and continue the loop
                        #side1 = (current_side[0], other_vertex)
                        #if intersects(side1, e):
                            #other_vertex = edges_lookup[side1[::-1]]
                            #current_side = side1
                            #remove_tri(*(current_side+(other_vertex, )))
                        #else:
                            #side2 = (other_vertex, current_side[1])
                            #if intersects(side2, e):
                                #other_vertex = edges_lookup[side2[::-1]]
                                #current_side = side2
                                #remove_tri(*(current_side+(other_vertex, )))
                            #else:
                                ## edge passes through the other_vertex
                                #debug("    does not intersect any other side, "
                                    #"need to handle it")
                                #break

                        #if orientation((i, endpoint), current_side[0]) > 0:
                            #upper_polygon.append(current_side[0])
                            #lower_polygon.append(current_side[1])
                        #else:
                            #upper_polygon.append(current_side[1])
                            #lower_polygon.append(current_side[0])

                #upper_polygon = list(OrderedDict.fromkeys(upper_polygon))
                #lower_polygon = list(OrderedDict.fromkeys(lower_polygon))
                #upper_polygon.append(endpoint)
                #lower_polygon.append(endpoint)

                    
        self.finalize()
        
        self.tris = np.array(self.tris, dtype=int)
        
    def finalize(self):
        ## Finalize (sec. 3.5)

        # (i) Remove all triangles that include at least one artificial point
        #debug("== Remove artificial triangles")
        ## todo: just don't add these in the first place. 
        #rem = []
        #for tri in self.tris:
            #if 0 in tri or 1 in tri:
                #rem.append(tri)
                
        #for tri in rem:
            #self.remove_tri(*tri)


        # (ii) Add bordering triangles to fill hull
        debug("== Fill hull")
        front = list(OrderedDict.fromkeys(self.front))

        l = len(front) - 2
        k = 1
        while k < l-1:
            # if edges lie in counterclockwise direction, then signed area is positive
            if self.iscounterclockwise(front[k], front[k+1], front[k+2]):
                self.add_tri(front[k], front[k+1], front[k+2], legal=False, source='fill_hull')
                front.pop(k+1)
                l -= 1
                continue
            k += 1

        # (iii) Remove all triangles not inside the hull (not described in article)
        debug("== Remove triangles outside hull")

        # TODO:  Start off by marking all triangles connected to artificial points as
        #        "bad". Two triangles that share a hull edge are marked opposite, and
        #        triangles that share a non-hull edge are marked the same. This should
        #        take care of all artificial and hole triangles.
        # TODO:  We can remove (i) after this is implemented.
        tris = []  # triangles to check
        tri_state = {}  # 0 for outside, 1 for inside
        
        # find a starting triangle
        for t in self.tris:
            if 0 in t or 1 in t:
                tri_state[t] = 0
                tris.append(t)
                break
        
        while tris:
            debug("iterate:", tris)
            next_tris = []
            for t in tris:
                v = tri_state[t]
                for i in (0,1,2):
                    edge = (t[i], t[(i+1)%3])
                    pt = t[(i+2)%3]
                    t2 = self.adjacent_tri(edge, pt)
                    if t2 is None:
                        continue
                    t2a = t2[1:3] + t2[0:1]
                    t2b = t2[2:3] + t2[0:2]
                    if (t2 in tri_state or 
                        t2a in tri_state or t2b in tri_state):
                        continue
                    if self.is_constraining_edge(edge):
                        tri_state[t2] = 1 - v
                    else:
                        tri_state[t2] = v
                    next_tris.append(t2)
            tris = next_tris
        
        for t, v in tri_state.items():
            if v == 0:
                self.remove_tri(*t)

    def edge_event(self, i, j, front_index):
        """
        Force edge (i, j) to be present in mesh. 
        This works by removing intersected triangles and filling holes up to
        the cutting edge.
        """
        debug("  == edge event ==")
        pts = self.pts
        edges = self.edges
        front = self.front

        # First just see whether this edge is already present
        # (this is not in the published algorithm)
        if (i, j) in self.edges_lookup or (j, i) in self.edges_lookup:
            debug("    already added.")
            return
        debug("    Edge (%d,%d) not added yet. Do edge event. (%s - %s)" % (i, j, pts[i], pts[j]))
        
        # traverse in two different modes:
        #  1. If cutting edge is below front, traverse through triangles. These
        #     must be removed and the resulting hole re-filled. (fig. 12)
        #  2. If cutting edge is above the front, then follow the front until 
        #     crossing under again. (fig. 13)
        # We must be able to switch back and forth between these modes (fig. 14)

        # Collect points that draw the open polygons on either side of the cutting
        # edge. The final front must follow the upp
        upper_polygon = [i]
        lower_polygon = [i]
        
        # Keep track of which section of the front must be replaced
        # and with what it should be replaced
        front_holes = []  # contains start and stop indexes for sections of front to condense
        
        next_tri = None   # next triangle to cut (already set if in mode 1)
        last_edge = None  # or last triangle edge crossed (if in mode 1)
        
        # Which direction to traverse front
        front_dir = 1 if self.pts[j][0] > self.pts[i][0] else -1
                
        # Initialize search state
        if self.edge_below_front((i, j), front_index):
            mode = 1  # follow triangles
            tri = self.find_cut_triangle((i, j))
            last_edge = self.edge_opposite_point(tri, i)
            next_tri = self.adjacent_tri(last_edge, i)
            assert next_tri is not None
            self.remove_tri(*tri)
            # todo: does this work? can we count on last_edge to be clockwise
            # around point i?
            lower_polygon.append(last_edge[1])
            upper_polygon.append(last_edge[0])
        else:
            mode = 2  # follow front
            front_holes.append([front_index])
            front_index += front_dir
            lower_polygon.append(front[front_index])
            

        # Loop until we reach point j
        while True:
            debug("  edge_event loop: mode %d" % mode)
            debug("    front_holes:", front_holes, front)
            debug("    front_index:", front_index)
            debug("    next_tri:", next_tri)
            debug("    last_edge:", last_edge)
            debug("    upper_polygon:", upper_polygon)
            debug("    lower_polygon:", lower_polygon)
            if mode == 1:
                if self.edge_in_front(last_edge): # crossing over front
                    debug("    -> crossed over front..")
                    mode = 2
                    next_tri = None
                    # update front / polygons
                    front_index = x  # where did we cross the front?
                    front_holes.append([front_index]) 
                    continue
                else: # crossing from one triangle into another
                    debug("    -> next triangle..")
                    if j in next_tri:
                        debug("    -> hit endpoint!")
                        # reached endpoint! 
                        # update front / polygons
                        upper_polygon.append(j)
                        lower_polygon.append(j)
                        self.remove_tri(*next_tri)
                        break
                    else:
                        tri_edges = self.edges_in_tri_except(next_tri, last_edge)
                        last_last_edge = last_edge
                        # select the edge that is cut
                        last_edge = self.intersected_edge(tri_edges, (i,j))
                        print("intersected edge:", last_edge)
                        last_tri = next_tri
                        next_tri = self.adjacent_tri(last_edge, last_tri)
                        self.remove_tri(*last_tri)
                        assert next_tri is not None
                        
                        # update polygons:
                        if lower_polygon[-1] == next_tri[0]:
                            upper_polygon.append(next_tri[1])
                        elif lower_polygon[-1] == next_tri[1]:
                            upper_polygon.append(next_tri[0])
                        elif upper_polygon[-1] == next_tri[0]:
                            lower_polygon.append(next_tri[1])
                        elif upper_polygon[-1] == next_tri[1]:
                            lower_polygon.append(next_tri[0])
                        else:
                            raise RuntimeError("Something went wrong..")
                
                
            else:  # mode == 2
                front_index += front_dir
                if front[front_index] == j:
                    debug("    -> hit endpoint!")
                    # found endpoint!
                    lower_polygon.append(j)
                    front_holes[-1].append(front_index)
                    break
                next_edge = tuple(front[front_index:front_index+2])
                
                if self.edges_intersect((i, j), next_edge): # crossing over front into triangle
                    debug("    -> crossed over front..")
                    mode = 1
                    front_holes[-1].append(front_index)
                    # more..
                else:
                    debug("    -> next front edge..")
                    lower_polygon.append(front[front_index])
                    continue  # stay in mode 2, start next point
        
        
        debug("Finished edge_event:")
        debug("  front_holes:", front_holes)
        debug("  upper_polygon:", upper_polygon)
        debug("  lower_polygon:", lower_polygon)

        # (iii) triangluate empty areas
        
        debug("Filling edge_event polygons...")
        for polygon in [lower_polygon, upper_polygon]:
            dist = self.distances_from_line((i, j), polygon)
            debug("Distances:", dist)
            while len(polygon) > 2:
                i = np.argmax(dist)
                debug("Next index: %d" % i)
                self.add_tri(polygon[i], polygon[i-1],
                             polygon[i+1], legal=False, 
                             source='edge_event')
                polygon.pop(i)
                dist.pop(i)

        debug("Finished filling edge_event polygons.")
        
        # update front by removing points in the holes (places where front 
        # passes below the cut edge)
        if front_dir == 1:
            front_holes = front_holes[::-1]
        for hole in front_holes:
            ind = min(hole) + 1
            for num in range(max(hole) - ind):
                front.pop(ind)

        debug("Finished updating front after edge_event.")

        
    def find_cut_triangle(self, edge):
        """
        Return the triangle that has edge[0] as one of its vertices and is 
        bisected by edge.
        
        Return None if no triangle is found.
        """
        edges = [] # opposite edge for each triangle attached to edge[0]
        for tri in self.tris:
            if edge[0] in tri:
                edges.append(self.edge_opposite_point(tri, edge[0]))
                
        for oedge in edges:
            o1 = self.orientation(edge, oedge[0])
            o2 = self.orientation(edge, oedge[1]) 
            debug(edge, oedge, o1, o2)
            debug(self.pts[np.array(edge)])
            debug(self.pts[np.array(oedge)])
            if o1 != o2:
                return (edge[0], oedge[0], oedge[1])
        
        return None

    def edge_in_front(self, edge):
        """
        Return True if *edge* is in the current front.
        """
        e = (list(edge), list(edge)[::-1])
        for i in range(len(self.front)-1):
            if self.front[i:i+2] in e:
                return True
        return False

    def edge_opposite_point(self, tri, i):
        """
        Given a triangle, return the edge that is opposite point i.
        Vertexes are returned in the same orientation as in tri.
        """
        ind = tri.index(i)
        return (tri[(ind+1) % 3], tri[(ind+2) % 3])

    def adjacent_tri(self, edge, i):
        """
        Given a triangle formed by edge and i, return the triangle that shares
        edge. *i* may be either a point or the entire triangle.
        """
        if not np.isscalar(i):
            i = [x for x in i if x not in edge][0]

        try:
            pt1 = self.edges_lookup[edge]
            pt2 = self.edges_lookup[(edge[1], edge[0])]
        except KeyError:
            return None
            
        if pt1 == i:
            return (edge[1], edge[0], pt2)
        elif pt2 == i:
            return (edge[1], edge[0], pt1)
        else:
            raise RuntimeError("Edge %s and point %d do not form a triangle "
                               "in this mesh." % (edge, i))

    def edges_in_tri_except(self, tri, edge):
        """Return the edges in *tri*, excluding *edge*.
        """
        edges = [(tri[i], tri[(i+1)%3]) for i in range(3)]
        try:
            edges.remove(tuple(edge))
        except ValueError:
            edges.remove(tuple(edge[::-1]))
        return edges

    def edge_below_front(self, edge, front_index):
        """Return True if *edge* is below the current front. 
        
        One of the points in *edge* must be _on_ the front, at *front_index*.
        """
        f0 = self.front[front_index-1]
        f1 = self.front[front_index+1]
        return (self.orientation(edge, f0) > 0 and 
                self.orientation(edge, f1) < 0)

    def is_constraining_edge(self, edge):
        mask1 = self.edges == edge[0]
        mask2 = self.edges == edge[1]
        return (np.any(mask1[:,0] & mask2[:,1]) or 
                np.any(mask2[:,0] & mask1[:,1]))
    
    def intersected_edge(self, edges, cut_edge):
        """ Given a list of *edges*, return the first that is intersected by
        *cut_edge*.
        """
        for edge in edges:
            if self.edges_intersect(edge, cut_edge):
                return edge

    def find_edge_intersections(self):
        """
        Return a dictionary containing, for each edge in self.edges, a list
        of the positions at which the edge should be split.
        """
        edges = self.pts[self.edges]
        cuts = {}  # { edge: [(intercept, point), ...], ... }
        for i in range(edges.shape[0]-1):
            # intersection of edge i onto all others
            int1 = self.intersect_edge_arrays(edges[i:i+1], edges[i+1:])
            # intersection of all edges onto edge i
            int2 = self.intersect_edge_arrays(edges[i+1:], edges[i:i+1])
        
            # select for pairs that intersect
            mask1 = (int1 >= 0) & (int1 <= 1)
            mask2 = (int2 >= 0) & (int2 <= 1)
            mask3 = mask1 & mask2  # all intersections
            
            # compute points of intersection
            inds = np.argwhere(mask3)[:, 0]
            if len(inds) == 0:
                continue
            h = int2[inds][:, np.newaxis]
            pts = edges[i, 0][np.newaxis, :] * (1.0 - h) + edges[i, 1][np.newaxis, :] * h
            
            # record for all edges the location of cut points
            edge_cuts = cuts.setdefault(i, [])
            for j,ind in enumerate(inds):
                if 0 < int2[ind] < 1:
                    edge_cuts.append((int2[ind], pts[j]))
                if 0 < int1[ind] < 1:
                    other_cuts = cuts.setdefault(ind+i+1, [])
                    other_cuts.append((int1[ind], pts[j]))
        
        # sort all cut lists by intercept, remove duplicates
        for k,v in cuts.items():
            v.sort(key=lambda x: x[0])
            for i in range(len(v)-2, -1, -1):
                if v[i][0] == v[i+1][0]:
                    v.pop(i+1)
        return cuts

    def split_intersecting_edges(self):
        # we can do all intersections at once, but this has excessive memory
        # overhead.
        #int1 = self.intersection_matrix(edges)
        #int2 = int1.T
        
        # measure intersection point between all pairs of edges
        all_cuts = self.find_edge_intersections()

        # cut edges at each intersection
        add_pts = []
        add_edges = []
        for edge, cuts in all_cuts.items():
            if len(cuts) == 0:
                continue
            
            # add new points
            pt_offset = self.pts.shape[0] + len(add_pts)
            new_pts = [x[1] for x in cuts]
            add_pts.extend(new_pts)
            
            # list of point indexes for all new edges
            pt_indexes = range(pt_offset, pt_offset + len(cuts))
            pt_indexes.append(self.edges[edge, 1])
            
            # modify original edge
            self.edges[edge, 1] = pt_indexes[0]
            
            # add new edges
            new_edges = [[pt_indexes[i-1], pt_indexes[i]] for i in range(1, len(pt_indexes))] 
            add_edges.extend(new_edges)
            
            assert [21, 22] not in new_edges
                    
        if add_pts:
            add_pts = np.array(add_pts, dtype=self.pts.dtype)
            self.pts = np.append(self.pts, add_pts, axis=0)
        if add_edges:
            add_edges = np.array(add_edges, dtype=self.edges.dtype)
            self.edges = np.append(self.edges, add_edges, axis=0)

    def merge_duplicate_points(self):
        # generate a list of all pairs (i,j) of identical points
        dups = []
        for i in range(self.pts.shape[0]-1):
            test_pt = self.pts[i:i+1]
            comp_pts = self.pts[i+1:]
            eq = test_pt == comp_pts
            eq = eq[:, 0] & eq[:, 1]
            for j in np.argwhere(eq)[:,0]:
                dups.append((i, i+1+j))

        dups_arr = np.array(dups)
        # remove duplicate points
        pt_mask = np.ones(self.pts.shape[0], dtype=bool)
        for i, inds in enumerate(dups_arr):
            # remove j from points
            # (note we pull the index from the original dups instead of 
            # dups_arr because the indexes in pt_mask do not change)
            pt_mask[dups[i][1]] = False
            
            i, j = inds
            
            # rewrite edges to use i instead of j
            self.edges[self.edges == j] = i
            #assert not np.any(self.edges[:,0] == self.edges[:,1])
            
            # decrement all point indexes > j
            self.edges[self.edges > j] -= 1
            dups_arr[dups_arr > j] -= 1
        
        self.pts = self.pts[pt_mask]
    
    # Distance between points A and B
    def distance(self, A, B):
        n = len(A)
        assert len(B) == n
        return np.linalg.norm(np.array(list(A)) - np.array(list(B)))


    # Distance of a set of points from a given line
    def distances_from_line(self, edge, points):
        e1 = self.pts[edge[0]]
        e2 = self.pts[edge[1]]
        distances = []
        for i in points:
            p = self.pts[i]
            proj = self.projection(e1, p, e2)
            distances.append(((p - proj)**2).sum()**0.5)
        return distances
        #distances = []
        ## check if e is not just a point
        #l2 = float(self.distance(e1, e2))
        #l2 *= l2
        #if l2 == 0:
            #for p in points:
                #distances.append(self.distance(e1, self.pts[p]))
        #else:
            #for p in points:
                #t = float((self.pts[p] - e1).dot(e2 - e1)) / l2
                #if (t < 0.0):
                    #distances.append(self.distance(self.pts[p], e1))
                #elif (t > 0.0):
                    #distances.append(self.distance(self.pts[p], e2))
                #else:
                    #projection = e1 + t * (e2 - e1)
                    #distances.append(self.distance(self.pts[p], projection))
                #debug("    point %d dist=%f" % (p, distances[-1]))
        #return distances

    def projection(self, a, b, c):
        """Return projection of (a,b) onto (a,c)
        Arguments are point locations, not indexes.
        """
        ab = b - a
        ac = c - a
        return a + ((ab*ac).sum() / (ac*ac).sum()) * ac

    # Cosine of angle ABC
    def cosine(self, A, B, C):
        a, b, c = self.distance(B, C), self.distance(A, C), self.distance(A, B)
        return (a*a + c*c - b*b) / (2*a*c)


    # Cartesian coordinates of the point whose barycentric coordinates
    # with respect to the triangle ABC are [p,q,r]
    def barycentric(self, A, B, C, p, q, r):
        n = len(A)
        assert len(B) == len(C) == n
        s = p+q+r
        p, q, r = p/s, q/s, r/s
        return tuple([p*A[i]+q*B[i]+r*C[i] for i in range(n)])


    # Cartesian coordinates of the point whose trilinear coordinates
    # with respect to the triangle ABC are [alpha,beta,gamma]
    def trilinear(self, A, B, C, alpha, beta, gamma):
        a = distance(B, C)
        b = distance(A, C)
        c = distance(A, B)
        return barycentric(A, B, C, a*alpha, b*beta, c*gamma)

                
    # Cartesian coordinates of the circumcenter of triangle ABC
    def circuminfo(self, A, B, C):
        cosA = cosine(C, A, B)
        cosB = cosine(A, B, C)
        cosC = cosine(B, C, A)
        cc = trilinear(A, B, C, cosA, cosB, cosC)
        # returns circumcenter and circumradius
        return cc, distance(cc, A)


    # Check if the points lie in counter-clockwise order or not
    def iscounterclockwise(self, a, b, c):
        A = self.pts[a]
        B = self.pts[b]
        C = self.pts[c]
        return np.cross(B-A, C-B) > 0


    def intersection(self, edge1, edge2):
        """Return the intercept of the line defined by edge1 onto edge2.
        A value of 0 indicates intersection at edge2[0], and 1 indicates 
        intersection at edge2[1]."""
        global pts
        A = pts[edge1[0]]
        B = pts[edge1[1]]
        C = pts[edge2[0]]
        D = pts[edge2[1]]

        E = B-A
        F = D-C
        P = np.array([-E[1], E[0]])
        f = float(F.dot(P))
        if f == 0.:
            return float('Inf')
        h = float((A-C).dot(P))/f
        return h


    def edges_intersect(self, edge1, edge2):
        """
        Return 1 if edges intersect completely (endpoints excluded)
        """
        h12 = self.intersect_edge_arrays(self.pts[np.array(edge1)], 
                                         self.pts[np.array(edge2)])
        h21 = self.intersect_edge_arrays(self.pts[np.array(edge2)], 
                                         self.pts[np.array(edge1)])
        return (0 < h12 < 1) and (0 < h21 < 1)


    #def intersection_point(self, edge1, edge2):
        #"""Return the point at which two edges intersect, or None if they do not.
        #If edges intersect at their endpoints, return None.
        #"""
        #h1 = intersection(edge2, edge1)
        #h2 = intersection(edge1, edge2)
        #if (0 < h1 < 1) and (0 < h2 < 1):  # intersection at endpoints returns None
            #p0 = pts[edge1[0]]
            #p1 = pts[edge1[1]]
            #return p0 * (1.0 - h1) + p1 * h1
        #else:
            #return None

    def intersection_matrix(self, lines):
        """
        Return a 2D array of intercepts such that 
        intercepts[i, j] is the intercept of lines[i] onto lines[j].
        
        *lines* must be an array of point locations with shape (N, 2, 2), where
        the axes are (lines, points_per_line, xy_per_point).
        
        The intercept is described in intersect_edge_arrays().
        """
        return self.intersect_edge_arrays(lines[:, np.newaxis, ...], 
                                          lines[np.newaxis, ...])
        
        
    def intersect_edge_arrays(self, lines1, lines2):
        """Return the intercepts of all lines defined in *lines1* as they intersect
        all lines in *lines2*. 
        
        Arguments are of shape (..., 2, 2), where axes are:
        
        0: number of lines
        1: two points per line
        2: x,y pair per point

        Lines are compared elementwise across the arrays (lines1[i] is compared
        against lines2[i]). If one of the arrays has N=1, then that line is
        compared against all lines in the other array.
        
        Returns an array of shape (N,) where each value indicates the intercept
        relative to the defined line segment. A value of 0 indicates intersection
        at the first endpoint, and a value of 1 indicates intersection at the second
        endpoint. Values between 1 and 0 are on the segment, whereas values outside
        1 and 0 are off of the segment. 
        
        """
        #global pts
        #A = pts[edges1[:,0]]
        #B = pts[edges1[:,1]]
        #C = pts[edges2[:,0]]
        #D = pts[edges2[:,1]]
        
        l1 = lines1[..., 1, :] - lines1[..., 0, :]  # vector for each line in lines1
        l2 = lines2[..., 1, :] - lines2[..., 0, :]  # vector for each line in lines2
        diff = lines1[..., 0, :] - lines2[..., 0, :]  # vector between first point of each line
        #E = B - A
        #F = D - C
        
        p = l1.copy()[..., ::-1]  # vectors perpendicular to l1
        p[...,0] *= -1
        #P = E.copy()[:, ::-1] # perpendicular vectors
        #P[:,0] *= -1
        
        f = (l2 * p).sum(axis=-1)  # l2 dot p
        h = (diff * p).sum(axis=-1) / f  # diff dot p / f
        #h = ((A - C) * P).sum(axis=1) / f  # (A-C) dot P
        return h

    def orientation(self, edge, point):
        """Returns +1 if edge[0]->point is clockwise from edge[0]->edge[1], 
        -1 if counterclockwise, and 0 if parallel."""
        v1 = self.pts[point] - self.pts[edge[0]]
        v2 = self.pts[edge[1]] - self.pts[edge[0]]
        c = np.cross(v1, v2)  # positive if v1 is CW from v2
        return 1 if c > 0 else (-1 if c < 0 else 0)

    ## Legalize recursively - incomplete
    def legalize(self, p):
        return p  # disabled for now
    
        f00, f11, p = p

        debug("Legalizing points = {}, {}, {}".format(f00, f11, p))
        a = pts[f00]
        b = pts[f11]
        c = pts[p]
        cc, cr = circuminfo(a, b, c)
        for point in pts:
            if np.all(point == a) or np.all(point == b) or np.all(point == c):
                continue
            elif distance(cc, point) < cr:
                debug("Illegal point")
                debug(point)
                pass

        return (f00, f11, p)

    def add_tri(self, a, b, c, legal=True, source=None):
        # source is just used for debugging
        debug("Add triangle [%s]:" % source, (a,b,c))
        
        # sanity check
        assert a != b and b != c and c != a
        
        # ignore flat tris
        pa = self.pts[a]
        pb = self.pts[b]
        pc = self.pts[c]
        if np.all(pa == pb) or np.all(pb == pc) or np.all(pc == pa):
            debug("   Triangle is flat; refusing to add.")
            return
        
        # check this tri is unique
        for t in permutations((a,b,c)):
            if t in self.tris:
                raise Exception("Cannot add %s; already have %s" % ((a,b,c), t))
        
        # TODO: should add to edges_lookup after legalization??
        if self.iscounterclockwise(a, b, c):
            debug("    ", (a,b), (b,c), (c,a))
            self.edges_lookup[(a, b)] = c
            self.edges_lookup[(b, c)] = a
            self.edges_lookup[(c, a)] = b
        else:
            debug("    ", (b,a), (c,b), (a,c))
            self.edges_lookup[(b, a)] = c
            self.edges_lookup[(c, b)] = a
            self.edges_lookup[(a, c)] = b
        
        if legal:
            tri = self.legalize((a, b, c))
        else:
            tri = (a, b, c)
        
        self.tris.append(tri)


    def remove_tri(self, a, b, c):
        debug("Remove triangle:", (a,b,c))
        
        for k in permutations((a, b, c)):
            if k in self.tris:
                break
        self.tris.remove(k)
        (a, b, c) = k

        if self.edges_lookup.get((a, b), None) == c:
            #debug("    ", (a,b), (b,c), (c,a))
            del self.edges_lookup[(a, b)]
            del self.edges_lookup[(b, c)]
            del self.edges_lookup[(c, a)]
        elif self.edges_lookup.get((b, a), None) == c:
            #debug("    ", (b,a), (c,b), (a,c))
            del self.edges_lookup[(b, a)]
            del self.edges_lookup[(a, c)]
            del self.edges_lookup[(c, b)]
        else:
            raise RuntimeError("Lost edges_lookup for tri (%d, %d, %d)" % 
                               (a, b, c))

        return k

# Note: using custom debug instead of logging because 
# there are MANY messages and logger might be too expensive.
# After this becomes stable, we might just remove them altogether.
DEBUG = True
def debug(*args):
    if DEBUG:
        print(*args)



if __name__ == '__main__':
    import pyqtgraph as pg
    import time
    
    app = pg.mkQApp()
    
    class DebugTriangulation(Triangulation):
        """ 
        Visualize triangulation process stepwise to aid in debugging.
        
        *interval* specifies the diration to wait before drawing each update in
        the triangulation procedure. Negative values cause the display to wait
        until the user clicks on the window for each update.
        
        *skip* causes the display to immediately process the first N events
        before pausing.
        """
        def __init__(self, pts, edges, interval=0.01, skip=0):
            self.interval = interval
            self.iteration = 0
            self.skip = skip 
            
            Triangulation.__init__(self, pts, edges)
            
            # visual debugging: draw edges, front, triangles
            self.win = pg.plot()
            self.graph = pg.GraphItem(pos=pts.copy(), adj=edges.copy(), 
                                      pen={'width': 3, 'color': (0, 100, 0)})
            self.win.addItem(self.graph)
            self.front_line = pg.PlotCurveItem(pen={'width': 2, 
                                                    'dash': [5, 5], 
                                                    'color': 'y'})
            self.win.addItem(self.front_line)
            self.tri_shapes = {}
            
            self.nextStep = False
            self.win.scene().sigMouseClicked.connect(self.mouseClicked)

        def mouseClicked(self):
            self.nextStep = True
            
        def draw_state(self):
            global app
            print("State %s" % self.iteration)
            self.iteration += 1
            if self.iteration <= self.skip:
                return
            
            front_pts = self.pts[np.array(self.front)]
            self.front_line.setData(front_pts[:,0], front_pts[:,1])
            self.graph.setData(pos=self.pts, adj=self.edges) 
            
            # Auto-advance on timer
            if self.interval < 0:
                #Advance once per click
                while True:
                    app.processEvents()
                    time.sleep(0.01)
                    if self.nextStep:
                        self.nextStep = False
                        break
            else:
                for i in range(int(self.interval / 0.01)):  # sleep, but keep ui responsive
                    app.processEvents()
                    time.sleep(0.01)
                
                

        def draw_tri(self, tri, source=None):
            # assign triangle color based on the source that generated it
            color = {
                None: (0, 255, 255, 50),
                'smooth1': (0, 255, 0, 50),
                'fill_hull': (255, 255, 0, 50),
                'edge_event': (100, 100, 255, 100),
                }[source]
            
            tpts = self.pts[np.array(tri)]
            path = pg.arrayToQPath(tpts[:,0], tpts[:,1])
            shape = pg.QtGui.QGraphicsPathItem(path)
            shape.setPen(pg.mkPen(255, 255, 255, 100))
            brush = pg.mkBrush(color)
            shape.setBrush(brush)
            self.win.addItem(shape)
            self.tri_shapes[tri] = shape
            self.draw_state()

        def undraw_tri(self, tri):
            shape = self.tri_shapes.pop(tri)
            self.win.removeItem(shape)
            self.draw_state()
            
        def add_tri(self, *args, **kwds):
            Triangulation.add_tri(self, *args, **kwds)
            self.draw_tri(self.tris[-1], source=kwds.get('source', None))
        
        def remove_tri(self, *args, **kwds):
            k = Triangulation.remove_tri(self, *args, **kwds)
            self.undraw_tri(k)

        def edge_event(self, *args, **kwds):
            self.draw_state()
            Triangulation.edge_event(self, *args, **kwds)
            self.draw_state()
        
    #user input data - points and constraining edges
    
    #
    #  Test 1
    #
    pts = [(0, 0),
        (10, 0),
        (10, 10),
        (20, 10),
        (20, 20),
        (25, 20),
        (25, 25),
        (20, 25),
        (20, 20),
        (10, 17),
        (5, 25),
        (9, 30),
        (6, 15),
        (15, 12.5),
        (0, 5)]
    l = len(pts)
    edges = [(i, (i+1) % l) for i in range(l)]
    pts += [(21, 21),
            (24, 21),
            (24, 24),
            (21, 24)]
    edges += [(l,   l+1),
              (l+1, l+2),
              (l+2, l+3),
              (l+3, l)]

    pts1 = np.array(pts, dtype=float)
    edges1 = np.array(edges, dtype=int)


    #
    # Test 2
    #
    np.random.seed(0)
    pts2 = np.random.normal(size=(10, 2))
    edges2 = np.zeros((10, 2), dtype=int)
    edges2[:,0] = np.arange(10)
    edges2[:,1] = np.arange(1,11) % 10
    
    #
    # Test 3
    #
    pts3 = np.random.normal(size=(10, 2))
    edges3 = np.zeros((10, 2), dtype=int)
    edges3[:,0] = np.arange(10)
    edges3[:,1] = np.arange(1,11) % 10
    
    #
    # Test 4
    #
    pts4 = np.random.normal(size=(10, 2))
    edges4 = np.zeros((10, 2), dtype=int)
    edges4[:,0] = np.arange(10)
    edges4[:,1] = np.arange(1,11) % 10
    
    
    t = DebugTriangulation(pts4, edges4, interval=-1, skip=50)
    t.triangulate()




