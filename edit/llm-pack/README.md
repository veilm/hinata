wow! Unix-abiding code packaging into a prompt

# Basic usage
```sh
cd hinata/edit/llm-pack

# here's what we currently have in ./test-dir
$ tree ./test-dir
test-dir
├── dir1
│   └── file1.txt
├── god.txt
├── we_hate_js.js
└── year.txt

2 directories, 4 files

# let's pack all files... except for that stupid JS one..
# compile
$ ./build

# other utils like find or fd already have pattern matching. let's [E]xclude JS
$ fd . --type f -E "*.js" test-dir
test-dir/dir1/file1.txt
test-dir/god.txt
test-dir/year.txt

# wow imagine being so innovative that you decide to reimplement everything in fd
# in your LLM packing tool. that's not me so we'll continue using fd but spread
# its output as args to llm-pack, leveraging a subshell
$ llm-pack $(fd . --type f -E "*.js" test-dir)
<file_paths>
dir1/file1.txt
god.txt
year.txt
</file_paths>

<dir1/file1.txt>
this is file1
</dir1/file1.txt>

<god.txt>
nvda --> EL
</god.txt>

<year.txt>
2027
</year.txt>

# (llm-pack would also output the code fences for you. not shown here)
```

simple as. Is this really worth 15k GitHub stars?

# philosophy
- an initial file_paths list tells the LLM what to expect
- XML tags are unambiguous and generally unlikely to clash with content within the file
- it's easier to distinguish files with less of a shared directory path, so we print file paths relative to their closest shared root
