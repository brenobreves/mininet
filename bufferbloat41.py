from mininet.topo import Topo
from mininet.node import CPULimitedHost
from mininet.link import TCLink
from mininet.net import Mininet
from mininet.log import lg, info
from mininet.util import dumpNodeConnections
from mininet.cli import CLI

from subprocess import Popen, PIPE
from time import sleep, time
from multiprocessing import Process
from argparse import ArgumentParser

from monitor import monitor_qlen

import sys
import os
import math

parser = ArgumentParser(description="Bufferbloat tests")
parser.add_argument('--bw-host', '-B',
                    type=float,
                    help="Bandwidth of host links (Mb/s)",
                    default=1000)

parser.add_argument('--bw-net', '-b',
                    type=float,
                    help="Bandwidth of bottleneck (network) link (Mb/s)",
                    required=True)

parser.add_argument('--delay',
                    type=float,
                    help="Link propagation delay (ms)",
                    required=True)

parser.add_argument('--dir', '-d',
                    help="Directory to store outputs",
                    required=True)

parser.add_argument('--time', '-t',
                    help="Duration (sec) to run the experiment",
                    type=int,
                    default=10)

parser.add_argument('--maxq',
                    type=int,
                    help="Max buffer size of network interface in packets",
                    default=100)

# Linux uses CUBIC-TCP by default that doesn't have the usual sawtooth
# behaviour.  For those who are curious, invoke this script with
# --cong cubic and see what happens...
# sysctl -a | grep cong should list some interesting parameters.
# Expt parameters
args = parser.parse_args()

class BBTopo(Topo):
    "Simple topology for bufferbloat experiment."

    def build(self, n=2):
        # TODO: create two hosts
        host1 = self.addHost('h1')
        host2 = self.addHost('h2')
        host3 = self.addHost('h3')
        # Here I have created a switch.  If you change its name, its
        # interface names will change from s0-eth1 to newname-eth1.
        switch = self.addSwitch('s0')

        # TODO: Add links with appropriate characteristics
        self.addLink(host2,switch,bw=args.bw_host,delay=f"{args.delay}ms")
        self.addLink(switch,host1,bw=args.bw_net,delay=f"{args.delay}ms",max_queue_size=args.maxq)
        self.addLink(host3,switch,bw=args.bw_host,delay=f"{args.delay}ms")

# Simple wrappers around monitoring utilities.  You are welcome to
# contribute neatly written (using classes) monitoring scripts for
# Mininet!

def start_iperf(net):
    h1 = net.get('h1')
    h2 = net.get('h2')
    h3 = net.get('h3')
    print("Starting iperf server...")
    # For those who are curious about the -w 16m parameter, it ensures
    # that the TCP flow is not receiver window limited.  If it is,
    # there is a chance that the router buffer may not get filled up.
    h1.popen("iperf -s -p 5001 -w 16m")
    h1.popen("iperf -s -p 5002 -w 16m")
    sleep(1)
    # TODO: Start the iperf client on h1.  Ensure that you create a
    # long lived TCP flow.
    # client = ...
    h2.popen(f"iperf -c {h1.IP()} -p 5001 -t {args.time}")
    h3.popen(f"iperf -c {h1.IP()} -p 5002 -t {args.time}")
    print("client ok")

def start_qmon(iface, interval_sec=0.1, outfile="q.txt"):
    monitor = Process(target=monitor_qlen,
                      args=(iface, interval_sec, outfile))
    monitor.start()
    return monitor

def start_ping(net):
    # TODO: Start a ping train from h1 to h2 (or h2 to h1, does it
    # matter?)  Measure RTTs every 0.1 second.  Read the ping man page
    # to see how to do this.

    # Hint: Use host.popen(cmd, shell=True).  If you pass shell=True
    # to popen, you can redirect cmd's output using shell syntax.
    # i.e. ping ... > /path/to/ping.
    h1 = net.get('h1')
    h2 = net.get('h2')
    h3 = net.get('h3')
    ping2 = h2.popen(f'ping {h1.IP()} -i 0.1 > {args.dir}/ping41reno.txt', shell=True)
    ping3 = h3.popen(f'ping {h1.IP()} -i 0.1 > {args.dir}/ping41bbr.txt', shell=True)
    return [ping2, ping3]

def start_webserver(net):
    h1 = net.get('h1')
    proc = h1.popen("python webserver.py", shell=True)
    sleep(1)
    return [proc]

def fetch_html(net, client):
    h_client = net.get(client)
    h_server = net.get('h1')

    cmd = f"curl -o /dev/null -s -w %{{time_total}} http://{h_server.IP()}:8000"
    proc = h_client.popen(cmd, shell=True, stdout=PIPE, stderr=PIPE)
    output, error = proc.communicate()
    if not output:
        print("curl failed:", error.decode().strip())
        return None
    try:
        return float(output.decode().strip())
    except ValueError:
        print("invalid curl output:", output.decode())
        return None
def bufferbloat():
    if not os.path.exists(args.dir):
        os.makedirs(args.dir)
    os.system("sysctl -w net.ipv4.tcp_congestion_control=reno")
    topo = BBTopo()
    net = Mininet(topo=topo, host=CPULimitedHost, link=TCLink)
    net.start()
    h2 = net.get('h2')
    h3 = net.get('h3')
    h2.cmd("sysctl -w net.ipv4.tcp_congestion_control=reno")
    h3.cmd("sysctl -w net.ipv4.tcp_congestion_control=bbr")

    # This dumps the topology and how nodes are interconnected through
    # links.
    dumpNodeConnections(net.hosts)
    # This performs a basic all pairs ping test.
    net.pingAll()

    # TODO: Start monitoring the queue sizes.  Since the switch I
    # created is "s0", I monitor one of the interfaces.  Which
    # interface?  The interface numbering starts with 1 and increases.
    # Depending on the order you add links to your network, this
    # number may be 1 or 2.  Ensure you use the correct number.
    qmon = start_qmon(iface='s0-eth2',
                      outfile='%s/q.txt' % (args.dir))

    # TODO: Start iperf, webservers, etc.
    start_iperf(net)
    start_ping(net)
    start_webserver(net)

    # TODO: measure the time it takes to complete webpage transfer
    # from h1 to h2 (say) 3 times.  Hint: check what the following
    # command does: curl -o /dev/null -s -w %{time_total} google.com
    # Now use the curl command to fetch webpage from the webserver you
    # spawned on host h1 (not from google!)
    # Hint: Verify the url by running your curl command without the
    # flags. The html webpage should be returned as the response
    # Hint: have a separate function to do this and you may find the
    # loop below useful.
    start_time = time()
    lista_rtts_reno = []
    lista_rtts_bbr = []
    while (time() - start_time) < args.time:
        for i in range(3):
            rtt_reno = fetch_html(net, client='h2')
            if rtt_reno is not None:
                lista_rtts_reno.append(rtt_reno)
            rtt_bbr = fetch_html(net, client='h3')
            if rtt_bbr is not None:
                lista_rtts_bbr.append(rtt_bbr)
        sleep(5)
        elapsed = time() - start_time
        remaining_time = args.time - elapsed
        print("%.1fs left..." % max(0,remaining_time))
    avg_reno = sum(lista_rtts_reno) / len(lista_rtts_reno)
    print(f"Media Reno: {avg_reno}")
    avg_bbr = sum(lista_rtts_bbr) / len(lista_rtts_bbr)
    print(f"Media BBR: {avg_bbr}")

    var_reno = sum((rtt - avg_reno)**2 for rtt in lista_rtts_reno) / len(lista_rtts_reno)
    dev_reno = math.sqrt(var_reno)
    print(f"Desvio padrao Reno: {dev_reno}")

    var_bbr = sum((rtt - avg_bbr)**2 for rtt in lista_rtts_bbr) / len(lista_rtts_bbr)
    dev_bbr = math.sqrt(var_bbr)
    print(f"Desvio padrao BBR: {dev_bbr}")

    # TODO: compute average (and standard deviation) of the fetch
    # times.  You don't need to plot them.  Just note it in your
    # README and explain.

    # Hint: The command below invokes a CLI which you can use to
    # debug.  It allows you to run arbitrary commands inside your
    # emulated hosts h1 and h2.
    # CLI(net)

    qmon.terminate()
    net.stop()
    # Ensure that all processes you create within Mininet are killed.
    # Sometimes they require manual killing.
    Popen("pgrep -f webserver.py | xargs kill -9", shell=True).wait()

if __name__ == "__main__":
    bufferbloat()
