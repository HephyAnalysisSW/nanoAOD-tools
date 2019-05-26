import ROOT
import math, os,re,copy
import numpy as np
ROOT.PyConfig.IgnoreCommandLineOptions = True

from PhysicsTools.NanoAODTools.postprocessing.framework.datamodel import Collection, Object
from PhysicsTools.NanoAODTools.postprocessing.framework.eventloop import Module
from PhysicsTools.NanoAODTools.postprocessing.tools import matchObjectCollection, matchObjectCollectionMultiple
from PhysicsTools.NanoAODTools.postprocessing.modules.jme.JetReCalibrator import JetReCalibrator

class jetRecalib(Module):
    def __init__(self,  globalTag, jetType = "AK4PFchs", METBranchName="MET", unclEnThreshold=15):

        self.metBranchName = METBranchName
        self.unclEnThreshold = unclEnThreshold
        if "AK4" in jetType : 
            self.jetBranchName = "Jet"
        elif "AK8" in jetType :
            self.jetBranchName = "FatJet"
            self.subJetBranchName = "SubJet"
        else:
            raise ValueError("ERROR: Invalid jet type = '%s'!" % jetType)
        self.rhoBranchName = "fixedGridRhoFastjetAll"
        self.lenVar = "n" + self.jetBranchName
        # To do : change to real values
        self.jmsVals = [1.00, 0.99, 1.01]
        

        self.jesInputFilePath = os.environ['CMSSW_BASE'] + "/src/PhysicsTools/NanoAODTools/data/jme/"

        self.jetReCalibrator = JetReCalibrator(globalTag, jetType , True, self.jesInputFilePath, calculateSeparateCorrections = False, calculateType1METCorrection  = False)

        self.jetReCalibratorL1 = JetReCalibrator(globalTag, jetType , False, self.jesInputFilePath, calculateSeparateCorrections = True, calculateType1METCorrection  = False, upToLevel=1)
        # load libraries for accessing JES scale factors and uncertainties from txt files
        for library in [ "libCondFormatsJetMETObjects", "libPhysicsToolsNanoAODTools" ]:
            if library not in ROOT.gSystem.GetLibraries():
                print("Load Library '%s'" % library.replace("lib", ""))
                ROOT.gSystem.Load(library)

    def beginJob(self):
	pass

    def endJob(self):
	pass

    def beginFile(self, inputFile, outputFile, inputTree, wrappedOutputTree):
        self.out = wrappedOutputTree
        self.out.branch("%s_pt_nom" % self.jetBranchName, "F", lenVar=self.lenVar)
        self.out.branch("%s_pt_nom"%self.metBranchName , "F")
        self.out.branch("%s_phi_nom"%self.metBranchName, "F")
            
                        
    def endFile(self, inputFile, outputFile, inputTree, wrappedOutputTree):
        pass
    
    def analyze(self, event):
        """process event, return True (go to next module) or False (fail, go to next event)"""
        jets    = Collection(event, self.jetBranchName )
        met     = Object(event, self.metBranchName) 
        rawmet  = Object(event, "RawMET") 
        defmet  = Object(event, "MET") 
        muons   = Collection(event, "Muon") 

        jets_pt_nom = []
        ( met_px,         met_py        ) = ( met.pt*math.cos(met.phi),         met.pt*math.sin(met.phi) )
        ( def_met_px,     def_met_py    ) = ( defmet.pt*math.cos(defmet.phi),   defmet.pt*math.sin(defmet.phi) )
        ( raw_met_px,     raw_met_py    ) = ( rawmet.pt*math.cos(rawmet.phi),   rawmet.pt*math.sin(rawmet.phi) )

        rho = getattr(event, self.rhoBranchName)

        met_shift_x, met_shift_y = 0., 0.
        delta_x_T1Jet, delta_y_T1Jet = 0, 0
        delta_x_rawJet, delta_y_rawJet = 0, 0

        for jet in jets:
            # copy the jet_pt from the tuple
            jet_pt          = jet.pt
            rawFactor       = jet.rawFactor
            # get the raw jet pt
            jet_pt_raw      = jet.pt*(1 - jet.rawFactor)
            # get the corrected jet pt
            jet_pt_nom      = self.jetReCalibrator.correct(jet,rho)

            newjet = ROOT.TLorentzVector()
            newjet.SetPtEtaPhiM(jet.pt*(1-jet.rawFactor), jet.eta, jet.phi, jet.mass )
            muon_pt = 0
            if jet.muonIdx1>-1:
                newjet = newjet - muons[jet.muonIdx1].p4()
                muon_pt += muons[jet.muonIdx1].pt
            if jet.muonIdx2>-1:
                newjet = newjet - muons[jet.muonIdx2].p4()
                muon_pt += muons[jet.muonIdx2].pt

            jet.pt              = newjet.Pt()
            jet.rawFactor       = 0
            jet_pt_noMuL1L2L3   = self.jetReCalibrator.correct(jet,rho)   if self.jetReCalibrator.correct(jet,rho) > self.unclEnThreshold else jet.pt # only correct the non-mu fraction of the jet if it's above 15 GeV, otherwise take the raw pt
            jet_pt_noMuL1       = self.jetReCalibratorL1.correct(jet,rho) if self.jetReCalibrator.correct(jet,rho) > self.unclEnThreshold else jet.pt # only correct the non-mu fraction of the jet if it's above 15 GeV, otherwise take the raw pt


            # only correct the non-muon fraction of the jet for T1 MET. in fact, muon_pt should cancel out
            jet_pt_L1L2L3   = jet_pt_noMuL1L2L3 + muon_pt 
            jet_pt_L1       = jet_pt_noMuL1     + muon_pt 

            if jet_pt_nom < 0.0:
                jet_pt_nom *= -1.0
            jets_pt_nom    .append(jet_pt_nom)

            if self.metBranchName == 'METFixEE2017':
                # get the delta for removing L1L2L3-L1 corrected jets in the EE region from the default MET branch.
                # Right now this will only be correct if we reapply the same JECs,
                # because there's no way to extract the L1L2L3 and L1 corrections that were actually used as input to the stored type1 MET...
                if jet_pt_L1L2L3 > self.unclEnThreshold and 2.65<abs(jet.eta)<3.14 and jet_pt_raw < 50:
                    delta_x_T1Jet  += (jet_pt_L1L2L3-jet_pt_L1) * math.cos(jet.phi) + jet_pt_raw * math.cos(jet.phi)#jet_pt_raw * math.cos(jet.phi)
                    delta_y_T1Jet  += (jet_pt_L1L2L3-jet_pt_L1) * math.sin(jet.phi) + jet_pt_raw * math.sin(jet.phi)#jet_pt_raw * math.sin(jet.phi)

                # get the delta for removing raw jets in the EE region from the raw MET
                #if jet.pt > self.unclEnThreshold and 2.65<abs(jet.eta)<3.14 and jet.pt < 50:
                if jet_pt_L1L2L3 > self.unclEnThreshold and 2.65<abs(jet.eta)<3.14 and jet_pt_raw < 50:
                    delta_x_rawJet += jet_pt_raw * math.cos(jet.phi)#jet_pt_raw * math.cos(jet.phi)
                    delta_y_rawJet += jet_pt_raw * math.sin(jet.phi)#jet_pt_raw * math.sin(jet.phi)

            ## setting jet back to original values
            jet.pt          = jet_pt
            jet.rawFactor   = rawFactor

            #print
            #print "Next jet with:"
            #print "{:10}{:<10.2f}".format("raw pt", jet_pt_raw)
            #print "{:10}{:<10.2f}{:10}{:<10.2f}{:10}{:<10.2f}{:10}{:<10.2f}{:10}{:<10.2f}".format("L1L2L3 pt", jet_pt_L1L2L3, "L1 pt", jet_pt_L1, "muEF", jet.muEF, "chEmEF", jet.chEmEF, "neEmEF", jet.neEmEF)

            # only use jets with pt>15 GeV and EMF < 0.9 for T1 MET
            if jet_pt_L1L2L3 > self.unclEnThreshold and (jet.neEmEF+jet.chEmEF) < 0.9: # which one to use?
                jet_cosPhi = math.cos(jet.phi)
                jet_sinPhi = math.sin(jet.phi)
                if not ( self.metBranchName == 'METFixEE2017' and 2.65<abs(jet.eta)<3.14 and jet.pt*(1 - jet.rawFactor) < 50):

                    met_shift_x += (jet_pt_L1 - jet_pt_L1L2L3) * jet_cosPhi
                    met_shift_y += (jet_pt_L1 - jet_pt_L1L2L3) * jet_sinPhi
                    #print "{:10}{:<10.2f}{:10}{:<10.3f}".format("L1 x", jet_pt_L1*jet_cosPhi, "L1L2L3 x", jet_pt_L1L2L3*jet_cosPhi)
                    #print "{:10}{:<10.2f}{:10}{:<10.3f}".format("L1 y", jet_pt_L1*jet_sinPhi, "L1L2L3 y", jet_pt_L1L2L3*jet_sinPhi)
                    #print "{:10}{:<10.2f}{:10}{:<10.3f}{:10}{:<10.3f}".format("jet pt", jet_pt_L1L2L3, "x_shift", met_shift_x, "y_shift", met_shift_y)


        if self.metBranchName == 'METFixEE2017':
            # Remove the L1L2L3-L1 corrected jets in the EE region from the default MET branch
            def_met_px += delta_x_T1Jet
            def_met_py += delta_y_T1Jet

            # Remove raw jets in the EE region from RawMET
            raw_met_px += delta_x_rawJet
            raw_met_py += delta_y_rawJet

            # get unclustered energy part that is removed in the v2 recipe
            met_unclEE_x = def_met_px - met_px
            met_unclEE_y = def_met_py - met_py

            # finalize the v2 recipe for the rawMET by removing the unclustered part in the EE region
            raw_met_px -= met_unclEE_x
            raw_met_py -= met_unclEE_y


        met_px_nom = raw_met_px + met_shift_x
        met_py_nom = raw_met_py + met_shift_y

        self.out.fillBranch("%s_pt_nom" % self.jetBranchName, jets_pt_nom)
        self.out.fillBranch("%s_pt_nom" % self.metBranchName, math.sqrt(met_px_nom**2 + met_py_nom**2))
        self.out.fillBranch("%s_phi_nom" % self.metBranchName, math.atan2(met_py_nom, met_px_nom))        

        return True


# define modules using the syntax 'name = lambda : constructor' to avoid having them loaded when not needed

jetRecalib2017B = lambda : jetRecalib("Fall17_17Nov2017B_V6_DATA")
jetRecalib2017C = lambda : jetRecalib("Fall17_17Nov2017C_V6_DATA")
jetRecalib2017D = lambda : jetRecalib("Fall17_17Nov2017D_V6_DATA")
jetRecalib2017E = lambda : jetRecalib("Fall17_17Nov2017E_V6_DATA")
jetRecalib2017F = lambda : jetRecalib("Fall17_17Nov2017F_V6_DATA")
