#!/usr/bin/env python
# Authored by Ilya Goldberg (igg at cathilya dot org), Oct., 2013
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# 
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import os
import sys
import re
import struct
import array
import time
import datetime as dt
has_IJ = False
has_Tkinter = False
try:
	import ij
	has_IJ = True
except:
	try:
		# Using Tkinter for GUI
		import Tkinter as tk
		import tkFileDialog as tkfd
		import Tkconstants as tkcnst
		import ttk
		has_Tkinter = True
	except:
		pass
log_str = ""

# Round the date to the nearest 1st of the month.
# N.B.: Expects date as an int in ISO date format (yyyymmdd), returns same format
def date_to_nearest_month (date):
	yy = int(date/10000)
	mm = int ( (date % yy) / 100)
	dd = int ( (date % yy) % (mm * 100))

	tm = dt.date(yy, mm, dd)
	# first of the birth month
	a = tm.replace (day=1)
	# first of the following month
	b = dt.date (yy + mm / 12, mm % 12 + 1, 1)
	# Which first is closer to the date?
	# Rounding favors birth month for equidistant dates
	if (b - tm).days < (tm - a).days:
		dob = b
	else:
		dob = a
	return (dob.year * 10000) + (dob.month * 100) + dob.day

# This raises an Exception if this is not a Stratec file, or returns True
# Only checks existence, stat, verifies file name pattern and minimum size
def is_Stratec_file (path):
	fname = os.path.basename(path)
	
	if not os.path.isfile(path):
		raise Exception ("File '"+path+"' is not a file")
	# File existence, name, readability and format validations
	# First, readability and length
	try:
		fsize = os.stat(path).st_size
	except Exception, e:
		raise Exception ("Could not stat file '"+path+"': "+str(e))

	# Name must match the I<digits>.M<2 digits> pattern
	p = re.compile(r"^i\d+\.m\d{2}$", re.IGNORECASE)
	if not p.match (fname):
		raise Exception ("Filename '"+path+"' does not match the recognized Stratec naming convention (I<digits>.M<2 digits>)")
	
	# File size must be > 1609 bytes
	if fsize < 1610:
		raise Exception ("File '"+path+"' is not large enough to be a Stratec file")

	return True

# This zeroes-out the Patient Name Pascal-style string at offset 1099 (41 bytes)
# and calls date_to_nearest_month on the patient DOB to set it to the nearest 1st of the month
# N.B.:  This month rounding implies that for e.g. a DOB of 1956-12-17 becomes 1957-01-01.
#        Month rounding favors the birth month for equidistant dates (1956-12-16 becomes 1956-12-01)
# Other than these header modifications, copies the file to the path_out file.
# returns False if file does not pass is_Stratec_file()
# Raises exception if file looks like a Stratec file, but cannot be read,
#   does not have the right internal format, or if scrubbed file cannot be written
def scrub_Stratec_file (path_in, path_out):

	# These validations do not result in an exception (i.e. the file can just be ignored)
	try:
		is_Stratec_file (path_in)
	except:
		return False

	fname = os.path.basename(path_in)

	# Other errors here will throw Exceptions
	# Try to open/read
	try:
		infile = open(path_in,'rb')
		header = array.array('c', infile.read())
		infile.close()
	except Exception, e:
		if infile and not infile.closed: infile.close()
		raise Exception ("Could not open/read File '"+path_in+"': "+str(e))

	# Pascal-style string at 1050 offset must end in ".typ" (ignoring case)
	strlen = ord(header[1050])
	if not header[1051:1051+strlen].tostring().lower().endswith ('.typ'):
		raise Exception ("File '"+path_in+"' does not appear to be a Stratec file")
	
	# End of file validations:
	# Scrub the file

	# DOB at offset 1091 as little-endian 32-bit int in ISO format (yyyymmdd)
	date = struct.unpack ('<I', header[1091:1091+4].tostring())[0] # little-endian
	# Round the date, and re-pack the result
	date = date_to_nearest_month (date)
	header[1091:1091+4] = array.array ('c', struct.pack('<I',date))
	struct.pack_into('<I', header, 1091, date)

	# Write a 40-character empty string (41 bytes of 0's) to zero-out the patient name
	struct.pack_into('40s', header, 1099, '')

	# open the modified file for writing, and dump out the scrubbed file.
	try:
		outfile = open (path_out, "wb")
		outfile.write (header.tostring())
		outfile.close()
	except Exception, e:
		if outfile and not outfile.closed: outfile.close()
		raise Exception ("Could not write modified file '"+path_out+"': "+str(e))

	return True

# returns a triple of ints: yyyy, mm, dd
def read_Stratec_date (header, offset):
	date = struct.unpack ('<I', header[offset:offset+4].tostring())[0] # little-endian
	yy = int(date/10000)
	mm = int ( (date % yy) / 100)
	dd = int ( (date % yy) % (mm * 100))
	return (yy,mm,dd)

def read_Stratec_int16 (header, offset):
	return struct.unpack ('<H', header[offset:offset+2].tostring())[0] # little-endian

def read_Stratec_int32 (header, offset):
	return struct.unpack ('<I', header[offset:offset+4].tostring())[0] # little-endian

# This is a Pascal-style string, with the length in the first byte
def read_Stratec_string (header, offset):
	strlen = ord(header[offset])
	return header[offset+1:offset+1+strlen].tostring()

# Reads a stratec header into a dictionary
def read_Stratec_header (path_in):

	header_fields = {}

	# These validations do not result in an exception (i.e. the file can just be ignored)
	try:
		is_Stratec_file (path_in)
	except:
		return None

	fname = os.path.basename(path_in)

	# Other errors here will throw Exceptions
	# Try to open/read
	try:
		infile = open(path_in,'rb')
		header = array.array('c', infile.read())
		infile.close()
	except Exception, e:
		if infile and not infile.closed: infile.close()
		raise Exception ("Could not open/read File '"+path_in+"': "+str(e))

	# Pascal-style string at 1050 offset must end in ".typ" (ignoring case)
	strlen = ord(header[1050])
	if not header[1051:1051+strlen].tostring().lower().endswith ('.typ'):
		raise Exception ("File '"+path_in+"' does not appear to be a Stratec file")
	
	# End of file validations:

	# MeasDate @ 986
	(header_fields['meas_yy'], header_fields['meas_mm'], header_fields['meas_dd']) = read_Stratec_date (header,986)
	
	# PatMeasNo @ 1085
	header_fields['meas_no'] = read_Stratec_int16 (header, 1085)
	
	# PatNo @ 1087
	header_fields['pat_no'] = read_Stratec_int32 (header, 1087)

	# DOB at offset 1091 as little-endian 32-bit int in ISO format (yyyymmdd)
	(header_fields['dob_yy'], header_fields['dob_mm'], header_fields['dob_dd']) = read_Stratec_date (header,1091)

	# PatName @ 1099
	header_fields['pat_name'] = read_Stratec_string (header, 1099)

	# PatID @ 1282
	header_fields['pat_ID'] = read_Stratec_string (header, 1282)

	return header_fields

def print_Stratec_header (path_in):
	header_fields = read_Stratec_header (path_in)
	if (header_fields):
		column_list = (
			path_in,
			str(header_fields['pat_no']),
			str(header_fields['dob_yy']).zfill(4)+'-'+str(header_fields['dob_mm']).zfill(2)+'-'+str(header_fields['dob_dd']).zfill(2),
			str(header_fields['meas_yy']).zfill(4)+'-'+str(header_fields['meas_mm']).zfill(2)+'-'+str(header_fields['meas_dd']).zfill(2),
			str(header_fields['meas_no'])
		)
		print  "\t".join (column_list)

def quit():
	sys.exit(0)

def empty_evt(evt):
	return "break"

def save_log():
	file_out = tkfd.asksaveasfile(title="Save log as...")
	file_out.write(log_str)
	file_out.close()
	
def view_log ():
	global log_str

	top = tk.Toplevel()
	top.title("Stratec pQCT File Scrubber Log")

	msg = tk.Text(top, font=("Courier", 12))

	msg.bind("<Key>", empty_evt)
	msg.insert(tkcnst.END, log_str)
	msg.config(state=tkcnst.NORMAL) # text editing
	msg.pack()

	but_frame = tk.Frame(top)

	save_button = tk.Button(but_frame, text="Save", command=save_log)
	save_button.pack(pady=10, padx=10, side=tkcnst.LEFT)

	close_button = tk.Button(but_frame, text="Close", command=top.destroy)
	close_button.pack(pady=10, padx=10, side=tkcnst.LEFT)

	but_frame.pack(side=tkcnst.BOTTOM, anchor=tkcnst.W)

def process_files (in_dir, out_dir):
	global log_str

	yield len([name for name in os.listdir(in_dir)])
	for file in os.listdir(in_dir):
		path = os.path.join(in_dir, file)
		scrubbed = None
		try:
			scrubbed = scrub_Stratec_file (path, os.path.join(out_dir, file))
		except Exception, e:
			log_str += str(e)+"\n"

		if not scrubbed:
			log_str += path+": ignored."+"\n"
		else:
			log_str += path+": scrubbed."+"\n"
		yield path
	yield None




def idle_task_tk (root, progressbar, iterator):
	try:
		if (progressbar["value"] == 0):
			progressbar["maximum"] = iterator.next()
		if iterator.next():
			progressbar["value"] = progressbar["value"] + 1
			root.after (0, idle_task_tk, root, progressbar, iterator)
	except:
		return

def idle_task_ij (iterator):
	global log_str
	index = 0
	numfiles = iterator.next()
	try:
		while (iterator.next()):	
			index += 1
			ij.IJ.showProgress(index, numfiles)
			ij.IJ.log(log_str)
			log_str = ""
	except Exception, e:
		ij.IJ.log(str(e)+"\n")


	

def idle_task_CLI (iterator):
	index = 0
	numfiles = iterator.next()
	while (iterator.next()):	
		index += 1

	ij.IJ.log(log_str)
	

def tkGUI():
	root = tk.Tk();
	root.title('Stratec pQCT File Scrubber')
	tk.Label (root,
		text ="Scrub sensitive patient/participant info from Stratec pQCT files",
		font=("Helvetica", 18, "bold"),
		).pack(pady=5, padx=10, anchor=tkcnst.W)
	tk.Label (root,
		text ="* Replace date of birth with the 1st of nearest month\n"+
		"* Zero-out patient name field",
		font=("Helvetica", 16),
		justify=tkcnst.LEFT,
		).pack(pady=10, padx=10, anchor=tkcnst.W)
	step_label = tk.StringVar()
	step_label.set ("\nStep 1: Select folder with Stratec files\n")
	tk.Label (root,
		textvariable = step_label,
		font=("Helvetica", 16, "bold"),
		justify=tkcnst.LEFT,
		).pack(pady=10, padx=10, anchor=tkcnst.W)

	dir_in = tkfd.askdirectory(mustexist=True,title="Select folder with Stratec files")
	if not dir_in:
		quit()
	
	step_label.set ("\nStep 2: Select folder for scrubbed Stratec files\n")
	dir_out = tkfd.askdirectory(mustexist=False,title="Select folder for scrubbed files")
	if not dir_out:
		sys.exit(0)
	step_label.set ("\n'"+dir_in+"' -> '"+dir_out+"'\n")

	# update here to get the current size of root
	root.update()
	progressbar = ttk.Progressbar (orient=tkcnst.HORIZONTAL, length=root.winfo_reqwidth()-40, mode='determinate')	
	progressbar["value"] = 0
	progressbar.pack()

	but_frame = tk.Frame(root)
	exit_button = tk.Button(but_frame, text="Quit", command=quit)
	exit_button.pack(pady=10, padx=10, side=tkcnst.LEFT)

	log_button = tk.Button(but_frame, text="View Log", command=view_log)
	log_button.pack(pady=10, padx=10, side=tkcnst.LEFT)
	but_frame.pack(side=tkcnst.BOTTOM, anchor=tkcnst.W)
	
	# Register an idle task to process the files
	idle_task_tk (root, progressbar, process_files (dir_in, dir_out))
	root.mainloop()

def ijGUI():
	from ij.io import DirectoryChooser
	dc = DirectoryChooser("Choose directory with Stratec files to scrub")
	dir_in = dc.getDirectory()
	dc = DirectoryChooser("Choose directory to write scrubbed files")
	dir_out = dc.getDirectory()
	idle_task_ij (process_files (dir_in, dir_out))


from optparse import OptionParser
from optparse import IndentedHelpFormatter
import textwrap
class IndentedHelpFormatterWithNL(IndentedHelpFormatter):
	def format_description(self, description):
		if not description: return ""
		desc_width = self.width - self.current_indent
		indent = " "*self.current_indent
		# the above is still the same
		bits = description.split('\n')
		formatted_bits = [
			textwrap.fill(bit,
				desc_width,
				initial_indent=indent,
				subsequent_indent=indent)
			for bit in bits]
		result = "\n".join(formatted_bits) + "\n"
		return result


def CLI():
	parser = OptionParser(add_help_option = False, formatter = IndentedHelpFormatterWithNL(),
		usage="usage: %prog [options] source-file(s)/directory [destination file/directory]",
		description="This program modifies the headers of Stratec pQCT files to zero-out "+
		"the Patient Name and round the DOB to the 1st of the nearest month.\n"+
		"Month rounding causes a DOB of 1956-12-17 to be changed to 1957-01-01, "+
		"and 1956-12-16 to be changed to 1956-12-01 (birth month is favored for midway dates).\n"+
		"Without any parameters, this script will launch a Tkinter-based GUI interface.\n\n"+
		"N.B.: It is entirely your responsibility to ensure the data is scrubbed properly."
	)
	parser.add_option("-d", dest="dump", action="store_true", default=False,
		help="dump file info only (path, pat. no., pat. DOB, meas. date, meas. no.), tab-delimited")
	parser.add_option("-f", dest="force", action="store_true", default=False,
		help="force in-place conversion without verification when no destination is specified")
	parser.add_option("-q", dest="quiet", action="store_true", default=False,
		help="don't print progress information to stdout")
	parser.add_option("-h", dest="help", action="store_true", default=False,
		help="show this help message and exit")

	(options, args) = parser.parse_args()
	if options.help:
		parser.print_help()
		quit()

	# destination is specified if the last argument is a directory,
	# or if there are two arguments, the first is a file, and the last argument does not exist
	src_files = []
	dst_files = []
	if (len (args) > 1 and os.path.isdir(args[len(args)-1])):
		dest_dir = args[len(args)-1]
		if (len (args) == 2) and os.path.isdir(args[0]):
			for name in os.listdir(args[0]):
				src = os.path.join(args[0], name)
				dst = os.path.join(dest_dir, name)
				if os.path.isfile (src):
					src_files.append (src)
					dst_files.append (dst)
		else:
			for src in args[0:len(args)-1]:
				dst = os.path.join(dest_dir, os.path.basename(src))
				if os.path.isfile (src):
					src_files.append (src)
					dst_files.append (dst)
				else:
					sys.stderr.write(src+" is not a file")

		options.force = True
		sources = args[0:len(args)-1]
		
	elif (len (args) == 2 and os.path.isfile(args[0]) and not os.path.exists(args[1])):
		dst_files = [args[1]]
		options.force = True
		sources = args[0]

	elif len (args) == 1 and os.path.isdir(args[0]):
		for name in os.listdir(args[0]):
			src = os.path.join(args[0], name)
			if os.path.isfile (src):
				src_files.append (src)
				dst_files.append (src)

	else:
		src_files = dst_files = args

	if (len (src_files) == 0):
		parser.error("At least one valid source file or directory must be specified")


	for index in range (0,len(src_files)):
		if not options.force and not options.dump:
			sys.stdout.write("process "+src_files[index]+"? [y/N/all]: ")
			choice = raw_input().lower()
			if not choice: choice = 'n'
			if choice.startswith ('a'):
				options.force = True
			elif not choice == 'y':
				continue

		try:
			if not options.dump:
				scrubbed = scrub_Stratec_file (src_files[index], dst_files[index])
			else:
				print_Stratec_header (src_files[index])
		except Exception as ex:
			sys.stderr.write(str(type(ex))+': '+str(ex)+"\n")
			raise

		if not options.quiet and not options.dump:
			if scrubbed:
				print src_files[index] + ": scrubbed."
			else:
				print src_files[index] + ": ignored."
	return

def main():
	if has_IJ:
		ijGUI()
	elif has_Tkinter and len(sys.argv) == 1:
		tkGUI()
	else:
		CLI()


if __name__ == "__main__":
    main()
