#!/usr/bin/env python

from __future__ import print_function

try:
  from urllib.parse import urlparse
  from urllib.request import urlopen, URLError
except ImportError:
  from urlparse import urlparse
  from urllib2 import urlopen, URLError

from argparse import ArgumentParser

import hashlib
import os
import sys
import errno
import fnmatch

usage = """make-prefetch.py [options] <file, url or directory>

Create a prefetch statement for BigFix ActionScript

Options:
  -a, --algorithm ALGORITHM      Hash algorithm to use (all, sha1, sha256)
                                 default: all
  -n, --name NAME                The name to use for the file
                                 default or when a directory is used: the name of the file
  -u, --url URL                  The url to use for the file
                                 default: the url of the file
                                 Note: the manifest format appends the filename to the provided url
  -o, --output OUTPUT            Output format (prefetch, davis, value, manifest)
                                 default: prefetch
  -f, --file_output FILE_OUTPUT  A file to write the output to
  -r, --recursive RECURSIVE      Recursively process the source directory
  -p, --pattern PATTERN          A wildcard pattern used when processing a source directory
                                 default: "*.*"
  -h, --help                     Print this help message and exit
  -v, --verbose                  Print additional output messages to aid in troubleshooting

Examples:
  Create a prefetch statement from a URL:

    make-prefetch.py http://example.com/hello.txt

  Create a prefetch statement from a file:

    make-prefetch.py hello.txt

  Create a prefetch statement from a directory:

    make-prefetch.py "C:\Temp\BigFix\ManifestSource"

  Create a 9.0 style prefetch statement:

    make-prefetch.py --algorithm sha1 hello.txt

  Create a 7.2 style prefetch statement:

    make-prefetch.py --algorithm sha1 --output davis hello.txt

  Process a certain type of files in a directory and output the prefetches to a file:

    make-prefetch.py -o manifest -p "*.bfa" -r -f "C:\Temp\BigFix\manifest.txt" "C:\Temp\BigFix\ManifestSource"
"""

def process_file(file_path, file_name, file_url):
  size = 0
  file_via_url = "://" in file_path

  if args.verbose: print("File source is a url.") if file_via_url else print("File source is the filesystem.")

  if file_name == '':
    file_name = 'REPLACEME'
    if args.verbose: print("Name provided was an empty string, using '{0}' instead. If you want to use the actual filename, don't pass a 'name' argument.".format(file_name))
  
  if file_url == '':
    file_url = 'http://REPLACEME'
    if args.verbose: print("URL provided was an empty string, using '{0}' instead.".format(file_url))

  # Open the file object via either the filesystem or url.
  if file_via_url:
    name = os.path.basename(urlparse(file_path).path) if file_name == None else file_name
    url = file_path if file_url == None else file_url
    f = urlopen(file_path)
  else:
    name = os.path.basename(file_path) if file_name == None else file_name
    url = 'http://REPLACEME' if file_url == None else file_url
    f = open(file_path, 'rb')
  
  # Calculate the hashes.
  sha1 = hashlib.sha1()
  sha256 = hashlib.sha256()
  while True:
    chunk = f.read(4096)
    if not chunk:
      break    
    sha1.update(chunk)
    sha256.update(chunk)
    if file_via_url: size += len(chunk)

  # If an actual file was opened, clean up and calculate the size.
  if not file_via_url:
    f.close()
    size = os.path.getsize(file_path)
  
  return {
    'name': name,
    'url': url,
    'size': size,
    'sha1': sha1.hexdigest(),
    'sha256': sha256.hexdigest()
  }

# Manifest output is for creating a manifest file which can be used for dynamic downloads.
def manifest_output(algorithm):
  if args.algorithm == 'sha256':
    return "name={name} sha256={sha256} size={size} url={url}/{name}"
  if args.algorithm == 'sha1':
    return "name={name} sha1={sha1} size={size} url={url}/{name}"
  return "name={name} sha1={sha1} sha256={sha256} size={size} url={url}/{name}"

def prefetch_output(algorithm):
  if args.algorithm == 'sha256':
    return "prefetch {name} size:{size} {url} sha256:{sha256}"
  if args.algorithm == 'sha1':
    return "prefetch {name} sha1:{sha1} size:{size} {url}"
  return "prefetch {name} sha1:{sha1} size:{size} {url} sha256:{sha256}"

def davis_output(algorithm, stage):
  if algorithm != 'all' and algorithm != 'sha1':
    print("Algorithm {0} is not supported in davis downloads".format(algorithm),
          file=sys.stderr)
    sys.exit(2)
  # Put this first as a shortcut for the possibility of numerous files coming through.
  if stage == 'middle':
    return ("add prefetch item name={name} sha1={sha1} size={size} url={url}")
  elif stage == 'beginning':
    return ("begin prefetch block")
  elif stage == 'end':
    return ("add prefetch item name={name} sha1={sha1} size={size} url={url}\n"
            "collect prefetch items\n"
            "end prefetch block")
  else:
    return ("begin prefetch block\n"
            "add prefetch item name={name} sha1={sha1} size={size} url={url}\n"
            "collect prefetch items\n"
            "end prefetch block")

def value_output(algorithm):
  if algorithm == 'sha1':
    return "{sha1}"
  if algorithm == 'sha256':
    return "{sha256}"
  print("You must specify a hash algorithm to use", file=sys.stderr)
  sys.exit(2)

parser = ArgumentParser(add_help=False, usage=usage)

parser.add_argument('source')

parser.add_argument(
  '-a',
  '--algorithm',
  choices=['all', 'sha1', 'sha256'],
  default='all')

parser.add_argument(
  '-o',
  '--output',
  choices=['value', 'davis', 'prefetch', 'manifest'],
  default='prefetch')

parser.add_argument('-n', '--name', required=False)
parser.add_argument('-u', '--url', required=False)
parser.add_argument('-f', '--file_output', required=False)
parser.add_argument('-r', '--recursive',  action='store_true', default=False, required=False)
parser.add_argument('-p', '--pattern', default='*.*', required=False)
parser.add_argument('-v', '--verbose', action='store_true', default=False)

if '-h' in sys.argv or '--help' in sys.argv:
  print(usage)
  sys.exit()

args = parser.parse_args()
counter = 1
matching_files = []

# If a directory was passed in, gather a list of files found.
if os.path.isdir(args.source):
  if args.verbose: print("{0} is a directory.".format(args.source))
  if args.output == 'davis': davis_stage = 'beginning'
    
  for root, dirnames, filenames in os.walk(args.source):
    if not args.recursive:
      while len(dirnames) > 0: dirnames.pop()
    for filename in fnmatch.filter(filenames, args.pattern):
      matching_files.append(os.path.join(root, filename))
  
  num_matches = len(matching_files)
  if num_matches == 0:
    print("No matching files found in '{0}'.".format(args.source), file=sys.stderr)
    sys.exit(2)
  
  if args.verbose:
    print("{0} matching file(s) found.".format(num_matches))
else:
  # A single file/url was passed in.
  matching_files.append(args.source)
  if args.output == 'davis': davis_stage = 'all'

# Process the list of files.
for matching_file in matching_files:
  if args.verbose: print("Processing {0}...({1} of {2})".format(matching_file, counter, num_matches))

  try:
    file = process_file(matching_file, args.name, args.url)
  except (URLError) as e:
    print("Error processing '{0}': {1}".format(args.source, e.reason), file=sys.stderr)
    sys.exit(2)
  except IOError, ioex:
    print("Error processing '{0}': {1}".format(args.source, os.strerror(ioex.errno)), file=sys.stderr)
    sys.exit(ioex.errno)
  except:
    print("Error processing '{0}'".format(args.source), file=sys.stderr)
    sys.exit(2)

  if args.output == 'manifest':
    output = manifest_output(args.algorithm)
  elif args.output == 'value':
    output = value_output(args.algorithm)
  elif args.output == 'davis':
    # Davis output needs special handling to insert multiple files
    # between the beginning and ending statements.
    if counter == num_matches: davis_stage = 'end'
    output = davis_output(args.algorithm, davis_stage)
    if davis_stage == 'beginning': davis_stage = 'middle'
  else:
    output = prefetch_output(args.algorithm)

  # Either output to the specified file or print to stdout.
  if args.file_output != None:
    if args.verbose: print("Writing output to {0}".format(args.file_output))
    with open(args.file_output,'a+') as out_file:
      out_file.write(output.format(name=file['name'],
                      size=file['size'],
                      url=file['url'],
                      sha1=file['sha1'],
                      sha256=file['sha256']) + '\n')
  else:
    print(output.format(name=file['name'],
                      size=file['size'],
                      url=file['url'],
                      sha1=file['sha1'],
                      sha256=file['sha256']))
  # Used mainly to know when to end the davis output, but also for verbose output.
  counter += 1
