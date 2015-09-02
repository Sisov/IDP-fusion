#!/usr/bin/python
import sys, os, re
import sequence_basics, aligner_basics, sam_basics, genepred_basics

# Pre:   <genome> - A fasta of the genome we are working with
#        <uniquely named short reads file> - can be generated by ./make_uniquely_named_short_read_file.py
#                                            can be a fastq or a fasta, and each name must be different
#        <transcriptome file> - A gene pred file containing definitions of different isoforms
#                               The names (column 2) of this file should be unique, and this is often not the case with the files that are downloaded
#        <output file> - File to write the results to (see post)
#        <temp folder name> - Name of a temporary folder we can work in
#        (optional)<genome bowtie2 index>
#        (optional)<transcriptome bowtie2 index> - This must be built on the directionless fasta generated from the <transcriptome file> genepred file
# Post:  Writes results to <output file>, and is two columns 
#        <read name> <mapping count>
#        So zero is unmapped to either genome or transcriptome,
#        1 is uniqely mapped to only one of them.
#        2 or more is a multimapped read.


def main():
  if len(sys.argv) < 6:
    print sys.argv[0] + ' <genome> <uniquely named short reads file> <transcriptome file> <output file> <temp directory>'
    sys.exit()

  genome_filename = sys.argv[1]
  sruniq_filename = sys.argv[2]
  transcriptome_filename = sys.argv[3]
  output_file = sys.argv[4]
  temp_foldername = sys.argv[5]
  genome_bowtie2_index = ''
  if len(sys.argv) >= 7:  genome_bowtie2_index = sys.argv[6]
  transcriptome_bowtie2_index = ''
  if len(sys.argv) == 8: transcriptome_bowtie2_index = sys.argv[7]

  if not os.path.isdir(temp_foldername):
    print "Error:  Expecting a temporary folder that already exists."
    print temp_foldername + " does not exist."
    sys.exit()

  #1. Make a sub-directory to do our work in
  local_temp_foldername = temp_foldername.rstrip('/')+'/uniqueness'
  if not os.path.isdir(local_temp_foldername):
    print "Creating subdirectory "+local_temp_foldername
    os.system("mkdir "+local_temp_foldername)



  #2. map reads to the genome fasta
  genome_base_name = local_temp_foldername.rstrip('/')+'/genome'
  sam_filename = local_temp_foldername.rstrip('/')+'/genome.sam'
  map_reads_to_fasta(genome_filename,sruniq_filename,genome_base_name,genome_bowtie2_index)
  
  #3.  count number of times we observe reads 
  read_counts = read_map_count(sruniq_filename, sam_filename)

  #4.  get unmapped reads into a fasta
  unmapped_read_names = get_unmapped_read_names(read_counts)
  unmapped_sruniq_filename = make_unmapped_short_read_file(sruniq_filename,unmapped_read_names,local_temp_foldername)

  #4. Make a fasta based on a transcriptome genepred file
  # first ensure the assumption that the genepred file contains only unqiuely named transcripts
  transcriptome_uniquename_filename = local_temp_foldername.rstrip('/')+'/txn_uniq.gpd'  
  genepred_basics.write_uniquely_named_genepred(transcriptome_filename,transcriptome_uniquename_filename)
  transcriptome_fa = local_temp_foldername.rstrip('/')+'/txn.fa'
  genepred_basics.write_genepred_to_fasta_directionless(transcriptome_uniquename_filename,genome_filename,transcriptome_fa)

  #5. Mapping previously unmapped reads to the transcriptome
  txn_base_name = local_temp_foldername.rstrip('/')+'/txn'
  txn_sam_filename = local_temp_foldername.rstrip('/')+'/txn.sam'
  map_reads_to_fasta(transcriptome_fa,unmapped_sruniq_filename,txn_base_name,transcriptome_bowtie2_index)
  
  #6. Convert coordinates of the mapped reads back to reference
  #   Note these coordinates are zero indexed for both start and end coordiantes.
  txn_map_filename = local_temp_foldername.rstrip('/') + '/txn.map'
  sam_basics.convert_directionless_gpd_alignment_to_reference(txn_sam_filename, transcriptome_uniquename_filename,txn_map_filename)
  
  #7. Consolidate repetative read mapping due to repeats junctions among isoforms
  txn_uniq_map_filename = local_temp_foldername.rstrip('/') + '/txn_uniq.map'
  # we are only interested in the unique coordinate sets for each entry
  os.system("cat "+txn_map_filename+" | cut -f 1,3 | sort | uniq > "+txn_uniq_map_filename)

  #8. Add transcriptome mapping counts
  transcriptome_read_counts = get_transcriptome_read_counts(txn_uniq_map_filename)
  #add those transcriptome_read_counts to our previous read counts
  for name in transcriptome_read_counts: read_counts[name]+=transcriptome_read_counts[name]

  #9. finished!  Now we can print the reads and their counts
  ofile = open(output_file,'w')
  for name in read_counts:
    ofile.write(name + "\t" + str(read_counts[name])+"\n")
  ofile.close()

# pre: transcriptome read mapping (of previously unmapped reads) in the format
#      <read name> <chromosome:coord1-coord2,coord3-coord4>
# post: for each read name count the number of times it seen and return it in a dictonary
def get_transcriptome_read_counts(txn_uniq_map_filename):
  c = {}
  with open(txn_uniq_map_filename) as tfile:
    for line in tfile:
      [name,coords] = line.rstrip().split("\t")
      if name not in c: c[name] = 0
      c[name]+=1
  return c

# pre: short read filename where all names are uniq (can be fasta of fastq, 
#      but if its fasta, it must be .fasta or .fa), and list of short read names
#      output file anme
# post: writes out a file of the short reads
def make_unmapped_short_read_file(sr_filename, names,tempfolder):
  isfasta = re.search('\.fa$|\.fasta$',sr_filename)
  outfile = tempfolder.rstrip('/')+'/'+'unmapped_shortread'
  if isfasta:
    outfile = outfile + '.fa'
    sequence_basics.write_fasta_subset(sr_filename,names,outfile)
  else:
    outfile = outfile + '.fq'
    sequence_basics.write_fastq_subset(sr_filename,names,outfile)
  return outfile

# pre: dictionary containing read names and the number of times they were mapped
# post: a list of unmapped read names
# modifies: none
def get_unmapped_read_names(read_counts):
  names = []
  for name in read_counts:
    if read_counts[name] == 0: 
      names.append(name)
  return names

# pre: short read filename with uniquely named reads, sam file name
# post: mapped reads and their counts in a dictionary keyed on read name
def read_map_count(sruniq_filename,sam_filename):
  print "get dictionary of names"
  reads = get_initialized_read_names(sruniq_filename)
  print "iterate over sam file counting reads"
  with open(sam_filename) as f:
    for line in f:
      line = line.rstrip()
      m = re.match('^@[A-Z][A-Z][\s]',line) #check for header
      if not m:
        [name,coordinate] = sam_basics.get_coordinates(line)
        if coordinate != '':
          reads[name]+=1
  return reads

# pre:  short read file with uniquely named reads (fasta or fastq)
#       if fasta, it needs extension fa or fasta
# post: a dictionary with read names as keys and entries set to zero
# modifies: none

def get_initialized_read_names(sruniq_filename):
  reads = {}
  if re.search('\.fa$|\.fasta$',sruniq_filename):
    reads = sequence_basics.counts_by_name_from_fasta(sruniq_filename)
  else:
    reads = sequence_basics.counts_by_name_from_fastq(sruniq_filename)
  for name in reads:
    reads[name] = 0
  return reads


# pre: temporary folder name, genome fasta file name,
#           file of short reads (fasta or fastq)
# post:     temporary folder containing genome.sam sam file of alignments
# modifies: builds an index for the genome fasta in the temporary folder
#           automatically sets processor count to use

def map_reads_to_fasta(fasta_filename,sr_name,base_name,bowtie2_index_base):
  sam_name = base_name + '.sam'

  #1.  See if we need an index.  this could be skipped if it is given as an input
  if bowtie2_index_base == '':
    print "create a bowtie2 index"
    aligner_basics.build_bowtie2_index(fasta_filename,base_name)
    bowtie2_index_base = base_name

  #2.  We align the reads
  print "align short reads to index with bowtie2"
  aligner_basics.bowtie2_unpaired(sr_name,bowtie2_index_base,sam_name)
  return sam_name

main()
