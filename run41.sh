#!/bin/bash

# Note: Mininet must be run as root.  So invoke this shell script
# using sudo.

mn -c

iperf_port=5001

for qsize in 20 100; do
    dir=bb-q$qsize

    # TODO: Run bufferbloat.py here...
    python3 bufferbloat41.py --bw-net=1.5 --bw-host=1000 --delay=5 --dir=$dir --maxq=$qsize --time=90

    # TODO: Ensure the input file names match the ones you use in
    # bufferbloat.py script.  Also ensure the plot file names match
    # the required naming convention when submitting your tarball.
    python3 plot_queue.py -f $dir/q.txt -o 41-buffer-q$qsize.png
    python3 plot_ping.py -f $dir/ping41reno.txt -o 41reno-rtt-q$qsize.png
    python3 plot_ping.py -f $dir/ping41bbr.txt -o 41bbr-rtt-q$qsize.png
done
