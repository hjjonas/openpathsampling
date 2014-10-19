'''
@author: JD Chodera
@author: JH Prinz
'''

import copy

import numpy as np
import mdtraj as md
from simtk.unit import nanometers


#=============================================================================================
# SIMULATION TRAJECTORY
#=============================================================================================

class Trajectory(list):
    """
    Simulation trajectory. Essentially a python list of snapshots

    """
    
    storage = None
    simulator = None
    default_storage = None

    def __init__(self, trajectory=None):
        """
        Create a simulation trajectory object

        Parameters
        ----------

        trajectory : Trajectory
            if specified, make a deep copy of specified trajectory
        """

        # Initialize list.
        list.__init__(self)

        self.idx = dict() # Contains references to positions in various files, will be set, once saved
        self.use_lazy = True    # We assume that snapshots are immutable. That should safe a lot of time to copy trajectories

        self.path_probability = None # For future uses

        if trajectory is not None:
            # Try to make a copy out of whatever container we were provided
            if hasattr(trajectory, 'atom_indices'):
                self.atom_indices = trajectory.atom_indices
            else:
                self.atom_indices = None
                
            if (self.use_lazy):
                self.extend(trajectory)
            else:
                for snapshot in trajectory:
                    snapshot_copy = copy.deepcopy(snapshot)
                    self.forward(snapshot_copy)
        else:
            self.atom_indices = None


    @property
    def reversed(self):
        '''
        Returns a reversed (shallow) copy of the trajectory itself.
        '''

        t = Trajectory(self)
        t.reverse()
        return t
    
    def reverse(self):
        """
        Reverse the trajectory.

        Notes
        -----        
        We cannot handle the velocities correctly when reversing the trajectory, so velocities will no longer be meaningful.
        Kinetic energies are correctly updated, however, and path actions should be accurate.

        """
        # Reverse the order of snapshots within the trajectory.
        list.reverse(self)

        # Determine number of snapshots.
#        nsnapshots = self.__len__()
        
        # Recalculate kinetic energies for the *beginning* of each trajectory segment.
        # This makes use of the fact that the energy is (approximately) conserved over each trajectory segment, in between velocity randomizations.
        # Note that this may be a poor approximation in some cases.
#        for t in range(nsnapshots-1):
#            self[t].kinetic_energy = self[t+1].total_energy - self[t].potential_energy

        # No use reversing momenta, since we can't determine what appropriate reversed momenta should be.
        
        # We could easily indicate reversed momenta by using a minus sign in front of the index
        # this keeps everything the same and we do not need to resave the snapshots and a -idx just means take snapshot idx but invert momenta

        for snapshot in self:
            snapshot.reversed = not snapshot.reversed
        
        return
    
    def coordinates(self):
        """
        Return all coordinates as a numpy array
        
        Returns
        -------        
        coordinates (numpy.array(n_frames, n_atoms, 3) - numpy.array of coordinates of size number of frames 'n_frames' x number of atoms 'n_atoms' x 3 in x,y,z
        """

        # Make sure snapshots are stored and have an index and then add the snapshot index to the trajectory

        n_frames = self.frames     
        n_atoms = self.atoms
            
        output = np.zeros([n_frames, n_atoms, 3], np.float32)
        
        for frame_index in range(n_frames):      
            if self.atom_indices is None:
                output[frame_index,:,:] = self[frame_index].coordinates
            else:
                output[frame_index,:,:] = self[frame_index].coordinates[self.atom_indices,:]
        
        return output
    
    @property
    def frames(self):
        """
        Return the number of frames in the trajectory
        
        Returns
        -------        
        length (int) - the number of frames in the trajectory
        
        """

        return len(self)
        
    def configuration_indices(self):
        """
        Return a list of the snapshot IDs in the trajectory
        
        Returns
        -------        
        indices (list of int) - the list of indices
        
        Notes
        -----        
        The IDs are only non-zero if the snapshots have been saved before!
        
        """
        return [f.configuration.idx for f in self]

    def configurations(self):
        """
        Return a list of the snapshot IDs in the trajectory

        Returns
        -------
        indices (list of int) - the list of indices

        Notes
        -----
        The IDs are only non-zero if the snapshots have been saved before!

        """
        return [f.configuration for f in self]


    def momenta(self):
        """
        Return a list of the snapshot IDs in the trajectory
        
        Returns
        -------        
        indices (list of int) - the list of indices
        
        Notes
        -----        
        The IDs are only non-zero if the snapshots have been saved before!
        
        """
        return [f.momenta.idx for f in self]

    
    @property
    def atoms(self):
        """
        Return the number of atoms in the trajectory in the current view. 
        
        Returns
        -------        
        n_atoms (int) - number of atoms

        Notes
        -----        
        If a trajectory has been subsetted then this returns only the number of the view otherwise if equals the number of atoms in the snapshots stored
        
        """

        if self.atom_indices is None:
            n_atoms = self[0].coordinates.shape[0]
        else:
            n_atoms = len(self.atom_indices)
        return n_atoms    
        
    #=============================================================================================
    # LIST INHERITANCE FUNCTIONS
    #=============================================================================================
    
    def as_list(self):
        """
        Return the contained list of snapshots as a python list object. Should not be necessary since
        we can just use list(self) to do so (DEPRECATED!)
        
        Returns
        -------        
        trajectory : list of Snapshot 
            the indexed trajectory
        
        """
        return list(self)

    def __getslice__(self, *args, **kwargs):
        ret =  super(Trajectory, self).__getslice__(*args, **kwargs)
        if isinstance(ret, list):
            ret = Trajectory(ret)
            ret.atom_indices = self.atom_indices
            
        return ret
        
    def __getitem__(self, index):
        # Allow for numpy style of selecting several indices using a list as index parameter
        if type(index) is list:
            ret = [ super(Trajectory, self).__getitem__(i) for i in index ]
        else:
            ret = super(Trajectory, self).__getitem__(index)
                
        if isinstance(ret, list):
            ret = Trajectory(ret)
            ret.atom_indices = self.atom_indices

        return ret
    
    def __add__(self, other):        
        t = Trajectory(self)
        t.extend(other)
        return t
    
    #=============================================================================================
    # PATH ENSEMBLE FUNCTIONS
    #=============================================================================================
    
    def pathHamiltonian(self):
        """
        Compute the generalized path Hamiltonian of the trajectory.

        Parameters
        ----------
        trajectory (Trajectory) - the trajectory

        Returns
        -------        
        H : simtk.unit.Quantity with units of energy
            the generalized path Hamiltonian

        References
        ----------       
        For a description of the path Hamiltonian, see [1]:

        [1] Chodera JD, Swope WC, Noe F, Prinz JH, Shirts MR, and Pande VS. Dynamical reweighting:
        Improved estimates of dynamical properties from simulations at multiple temperatures.    
        """

        nsnapshots = len(self)
        if nsnapshots > 0:
            H = self[0].total_energy
            for snapshot_index in range(1, nsnapshots-1):
                H += self[snapshot_index].kinetic_energy
        else:
            H = 0

        return H

    def computeActivity(self):
        """
        Compute the (timeless!) activity of a given trajectory, defined in Ref. [1] as

        K[x(t)] / delta_t = delta_t \sum_{t=0}^{t_obs} \sum_{j=1}^N [r_j(t+delta_t) - r_j(t)]^2 / delta_t

        RETURNS

        K (simtk.unit) - activity K[x(t)] for the specified trajectory
        
        NOTES
        
        Can we avoid dividing and multipying by nanometers to speed up?

        """

        # Determine number of frames in trajectory.
        nframes = len(self)

        # Compute activity of component A.
        K = 0.0 * nanometers**2
        for frame_index in range(nframes-1):
            # Compute displacement of all atoms.
            delta_r = self[frame_index+1].coordinates - self[frame_index].coordinates
            # Compute contribution to activity K.
            K += ((delta_r[0:self.N,:] / nanometers)**2).sum() * (nanometers**2)

        return K 
    
    def logEquilibriumTrajectoryProbability(self):
        """
        Compute the (temperatureless!) log equilibrium probability (up to an unknown additive constant) of an unbiased trajectory evolved according to Verlet dynamics with Andersen thermostatting.

        ARGUMENTS
        trajectory (Trajectory) - the trajectory

        Returns
        -------        
        log_q : float
            the log equilibrium probability of the trajectory divided by the inverse temperature beta
        
        NOTES
        This might be better places into the trajectory class. The trajectory should know the system and ensemble? and so it is not necessarily 
        TPS specific

        """

        nsnapshots = len(self)
        log_q = - self[0].total_energy
        for snapshot_index in range(1, nsnapshots-1):
            log_q += - self[snapshot_index].kinetic_energy

        return log_q

    
    #=============================================================================================
    # UTILITY FUNCTIONS
    #=============================================================================================

    def subset(self, atom_indices):
        """
        Reduce the view of the trajectory to a subset of atoms specified. This is only a view, no data will be changed or copied.
        
        Returns
        -------        
        trajectory : Trajectory
            the trajectory showing the subsets of atoms
        """        

        t = Trajectory(self)
        t.atom_indices = atom_indices
        return t

    @property
    def solute(self):
        """
        Reduce the view of the trajectory to a subset of solute atoms specified in the associated Simulator
        
        Returns
        -------        
        trajectory : Trajectory
            the trajectory showing the subsets of solute atoms
        """        

        return self.subset(Trajectory.simulator.solute_indices)

    def md(self, topology = None):
        """
        Construct a mdtraj.Trajectory object from the Trajectory itself
        
        Returns
        -------        
        trajectory : mdtraj.Trajectory
            the trajectory
        """

        output = self.coordinates()
        if topology is None:
            topology = self.md_topology()

        return md.Trajectory(output, topology)
                
    
    def md_topology(self):
        """
        Return a mdtraj.Topology object representing the topology of the current view of the trajectory
        
        Returns
        -------        
        topology : mdtraj.Topology
            the topology
        """        

        if hasattr(self[0], 'topology') and self[0].topology is not None:
            # if no topology is defined
            topology = self[0].topology
        else:
            # TODO: kind of ugly fall-back, but helps for now
            topology = md.Topology.from_openmm(Trajectory.simulator.simulation.topology)
        
        if self.atom_indices is not None:
            topology = topology.subset(self.atom_indices)       
        
        return topology

    #=============================================================================================
    # STORAGE FUNCTIONS
    #=============================================================================================

    def save(self):
        """
        Add the current state of the trajectory in the database. If nothing has changed then the trajectory gets stored using the same snapshots as before. Saving lots of diskspace

        Parameters
        ----------
        storage : TrajectoryStorage()
            If set this specifies the storage to be used. If the storage is None the default storage is used, which needs to
            be set in advance.

        Notes
        -----
        This also saves all contained frames in the trajectory if not done yet.
        A single Trajectory object can only be saved once!

        """
        self.storage.trajectory.save(self)