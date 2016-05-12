from django.shortcuts import render
from django.http import HttpResponse, HttpResponseRedirect
from django.template import loader
from .models import RNA
from Bio.Seq import Seq
from Bio import Entrez, SeqIO
import sys
sys.path.insert(0, '/Users/Yusef/Documents/Kitematic/crisprapp/hello_django_docker/sgRNA Design Tool/crispr_app/Rule_Set_2_scoring_v1/analysis')
sys.path.insert(0, 'Users/Yusef/Documents/bowtie/')
from rs2_score_calculator import calculateScore
import cPickle as pickle
import dill
import time
import subprocess
import os 
from operator import itemgetter

Entrez.email='yabourem@ucsd.edu'

def index(request):
	template = loader.get_template('crispr_app/index.html')
	sgRNAs = RNA.objects.all()

	context = {
		'sgRNAs' : sgRNAs,	
	}
	
	return HttpResponse(template.render(context,request))

def form(request):
	### TODO: upload button with fastq of sequences or accession numbers ###

	#Load Template
	template = loader.get_template('crispr_app/form.html')

	#Initialize context variables
	sequence = ''
	sgRNAInfo = []
	species = ''
	gi = ''
	start = ''
	stop = ''
	if request.method == 'POST':
		print request.POST.get('singleSeq')
		#Refresh page if fields empty
		if not request.POST.get('locus') and not request.POST.get('singleSeq'):
			return HttpResponse(template.render({}, request))

		#Get user input 
		if request.POST.get('locus'):
			gi = request.POST.get('locus')
		else:
			sequence = request.POST.get('singleSeq')
			print sequence
			sequence = sequence.strip().upper()
			if len(sequence) < 30:
				return HttpResponse(template.render({}, request))

		if request.POST.get('start'):	
			start = request.POST.get('start')
		if request.POST.get('end'):
			stop = request.POST.get('end')
		species = request.POST.get('species')

		#Fetch sequence data if needed
		if gi:
			Entrez.email = 'yabourem@ucsd.edu'
			if start and stop:
				handle = Entrez.efetch(db='nucleotide',id=gi,rettype='gb',retmode='text', seq_start=start, seq_stop=stop)
			else:
				handle = Entrez.efetch(db='nucleotide',id=gi,rettype='gb',retmode='text')
			time.sleep(1)
			record = SeqIO.read(handle, 'gb')
			sequence = record.seq
			handle.close()
			sequence = str(sequence)

		#Calculate scores of sequence, and collect other sgRNA information
		model_file = open('crispr_app/V3_model_nopos.pickle', 'rb')
		model = pickle.load(model_file)
		scores = []
		indices = []
		complements = []
		PAMs = []
		#5-->3
		for i in range(len(sequence) - 30):
			toScore = sequence[i:i+30]
			if len(toScore) == 30 and toScore[25:27] == 'GG':
				complements.append(toScore[4:24])
				PAMs.append(toScore[24:27])
				scores.append(calculateScore(toScore, model))
				#scores.append(1) 
				indices.append(i+21)

		#3-->5 (Reverse complement)
		mySeq = Seq(sequence)
		reverseComp = str(mySeq.reverse_complement())
		for i in range(len(reverseComp) - 30):
			toScore = reverseComp[i:i+30]
			if len(toScore) == 30 and toScore[25:27] == 'GG':
				complements.append(toScore[4:24])
				PAMs.append(toScore[24:27])
				scores.append(calculateScore(toScore, model)) 
				#scores.append(1)
				indices.append(len(sequence)-(i+21))
		
		#Calculate alignments of complement+PAM sequence via bowtie
		mismatch_dict = {}
		indexname = '/Users/Yusef/Documents/bowtie/indexes/GCA_000001405.15_GRCh38_no_alt_analysis_set'
		for i in range(len(complements)):
			molecule = complements[i] + PAMs[i]
			if RNA.objects.filter(sequence=molecule, species=species).count() == 1:
				continue
			mismatch_dict[molecule] = [-1, 0, 0, 0]
			alignments = subprocess.Popen(['/Users/Yusef/Documents/bowtie/bowtie', '-c', '-a', '-v 3', indexname, molecule], stdout=subprocess.PIPE)
			for line in alignments.stdout:
				mismatches = line.count(':')
				mismatch_dict[molecule][mismatches] += 1
			#Add the complement+PAM and alignment information to database
			rna = RNA.objects.create(sequence=molecule, species=species, 
				zero_mismatch_count=mismatch_dict[molecule][0], 
				one_mismatch_count=mismatch_dict[molecule][1], 
				two_mismatch_count=mismatch_dict[molecule][2], 
				three_mismatch_count=mismatch_dict[molecule][3])
			 
		#Visualize cut points in the sequence
		for cut in sorted(indices, reverse=True):
			sequence = sequence[:cut] + '['  + str(cut) + ']' + sequence[cut:]

		#Put all sgRNA info into one array
		#Note to self: careful with indices, as the user input starts at 1
		for i in range(len(scores)):
			rna = RNA.objects.get(sequence=complements[i]+PAMs[i], species=species)
			temp = [complements[i], PAMs[i], scores[i], indices[i], rna.zero_mismatch_count, 
			rna.one_mismatch_count, rna.two_mismatch_count, rna.three_mismatch_count]
			sgRNAInfo.append(temp)
		
	context = {
	'seq' : sequence,
	'sgRNAInfo' : sorted(sgRNAInfo, key=itemgetter(2)),
	'species' : species
	}
	return HttpResponse(template.render(context, request))


def result(request):
	template = loader.get_template('crispr_app/result.html')
	context = {
	}
	return HttpResponse(template.render(context, request))
