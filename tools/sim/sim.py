import argparse

from nmigen import *
from nmigen.back.pysim import *

from lambdausb.lib import stream
from lambdausb.cfg import ConfigurationEndpoint
from lambdausb.dev import UsbDevice
from lambdausb.protocol import Transfer

class UsbPhyModel():
    def __init__(self):
        self.source = stream.Endpoint([("data", 8)])
        self.sink = stream.Endpoint([("data", 8)])

    def send(self, packet):
        last = packet[-1]
        for byte in packet:
            yield self.source.valid.eq(1)
            yield self.source.data.eq(int(byte, 16))
            yield self.source.last.eq(byte is last)
            yield Tick()
            while not (yield self.source.ready):
                yield Tick()
        yield self.source.valid.eq(0)

    def receive(self):
        data = []
        yield self.sink.ready.eq(1)
        while True:
            if (yield self.sink.valid):
                data.append((yield self.sink.data))
                if (yield self.sink.last):
                    break
            yield Tick()
        yield self.sink.ready.eq(0)
        return data


from lambdausb.phy.usb import USBPHY

class USBPHY_Model(USBPHY):
    def send(self, packet):
        # last = packet[-1]
        for byte in packet:
            yield Cat(self.pins.p.i, self.pins.n.i).eq(int(byte, 16) & 0b11)
            yield Tick()
            # yield self.source.valid.eq(1)
            # yield self.source.data.eq(int(byte, 16))
            # yield self.source.last.eq(byte is last)
            # yield Tick()
            # while not (yield self.source.ready):
            #     yield Tick()
        # yield self.source.valid.eq(0)

    # def receive(self):
    #     data = []
    #     yield self.sink.ready.eq(1)
    #     while True:
    #         if (yield self.sink.valid):
    #             data.append((yield self.sink.data))
    #             if (yield self.sink.last):
    #                 break
    #         yield Tick()
    #     yield self.sink.ready.eq(0)
    #     return data


# FIXME rm
descriptor_map = {
	0x01: {0: (0,  18)},
	0x02: {0: (18,  25)},
	0x03: {
		 0: (43, 4),
		 1: (47, 28),
		 2: (75, 26),
		 3: (101, 8),
	},
	0x06: {0: (109, 10)},
	0x0a: {0: (119, 2)},
}
rom_init = [
	0x12, 0x01, 0x00, 0x02, 0x00, 0x00, 0x00, 0x40,
	0xac, 0x05, 0x78, 0x56, 0x00, 0x01, 0x01, 0x02,
	0x03, 0x01, 0x09, 0x02, 0x19, 0x00, 0x01, 0x01,
	0x00, 0xe0, 0x30, 0x09, 0x04, 0x00, 0x00, 0x01,
	0xff, 0x00, 0x00, 0x00, 0x07, 0x05, 0x01, 0x02,
	0x00, 0x02, 0x00, 0x04, 0x03, 0x09, 0x04, 0x1c,
	0x03, 0x4c, 0x00, 0x61, 0x00, 0x6d, 0x00, 0x62,
	0x00, 0x64, 0x00, 0x61, 0x00, 0x43, 0x00, 0x6f,
	0x00, 0x6e, 0x00, 0x63, 0x00, 0x65, 0x00, 0x70,
	0x00, 0x74, 0x00, 0x1a, 0x03, 0x62, 0x00, 0x6c,
	0x00, 0x69, 0x00, 0x6e, 0x00, 0x6b, 0x00, 0x65,
	0x00, 0x72, 0x00, 0x20, 0x00, 0x64, 0x00, 0x65,
	0x00, 0x6d, 0x00, 0x6f, 0x00, 0x08, 0x03, 0x31,
	0x00, 0x32, 0x00, 0x33, 0x00, 0x0a, 0x06, 0x00,
	0x02, 0x00, 0x00, 0x00, 0x40, 0x01, 0x00, 0x02,
	0x0a,
]


class UsbSimTop(Elaboratable):
    def __init__(self):
        # self.phy     = UsbPhyModel()

        from nmigen.lib.io import Pin
        p = Pin(1, dir="io")
        n = Pin(1, dir="io")
        usb_pins    = Record([("p", p.layout), ("n", n.layout)], fields={"p": p, "n": n})
        self.phy    = USBPHY_Model(usb_pins, 100e6)

        self.dev    = UsbDevice(self.phy)
        self.cfg_ep = ConfigurationEndpoint(descriptor_map, rom_init)
        self.cfg_wp = self.dev.input_port(0x0, 64, Transfer.CONTROL)
        self.cfg_rp = self.dev.output_port(0x0,  64, Transfer.CONTROL)
        self.rgb_rp = self.dev.output_port(0x1, 512, Transfer.BULK)

    def elaborate(self, platform):
        m = Module()

        m.submodules.phy    = self.phy
        m.submodules.dev    = self.dev
        m.submodules.cfg_ep = self.cfg_ep

        m.d.comb += [
            self.cfg_ep.source.connect(self.cfg_wp),
            self.cfg_rp.connect(self.cfg_ep.sink),
        ]

        return m


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    # parser.add_argument("sample", type=argparse.FileType("r"), help="sample file")
    parser.add_argument("-o", "--vcd", type=argparse.FileType("w"), default="trace.vcd", help="VCD output")
    args = parser.parse_args()

    dut = UsbSimTop()

    with Simulator(dut, vcd_file=args.vcd) as sim:
        def phy_rx_process():
            yield dut.phy.pins.p.i.eq(1)
            for _ in range(512):
                yield Tick()

            with open("ack.bin", "rb") as f:
                for sample in iter(lambda: f.read(2), b""):
                    yield Cat(dut.phy.pins.p.i, dut.phy.pins.n.i).eq(sample[0] & 0b11)
                    yield Tick()

            yield dut.phy.pins.p.i.eq(1)
            for _ in range(512):
                yield Tick()

            # with open("setup-data0.bin", "rb") as f:
            #     for sample in iter(lambda: f.read(2), b""):
            #         yield Cat(dut.phy.pins.p.i, dut.phy.pins.n.i).eq(sample[0] & 0b11)
            #         yield Tick()

            # yield dut.phy.pins.p.i.eq(1)
            # for _ in range(512):
            #     yield Tick()

            # with open("in.bin", "rb") as f:
            #     for sample in iter(lambda: f.read(2), b""):
            #         yield Cat(dut.phy.pins.p.i, dut.phy.pins.n.i).eq(sample[0] & 0b11)
            #         yield Tick()

            # yield dut.phy.pins.p.i.eq(1)
            # for _ in range(2048):
            #     yield Tick()

            # with open("in.bin", "rb") as f:
            #     for sample in iter(lambda: f.read(2), b""):
            #         yield Cat(dut.phy.pins.p.i, dut.phy.pins.n.i).eq(sample[0] & 0b11)
            #         yield Tick()

            # yield dut.phy.pins.p.i.eq(1)
            # for _ in range(2048):
            #     yield Tick()

#             with open("ack.bin", "rb") as f:
#                 for sample in iter(lambda: f.read(2), b""):
#                     yield Cat(dut.phy.pins.p.i, dut.phy.pins.n.i).eq(sample[0] & 0b11)
#                     yield Tick()

#             yield dut.phy.pins.p.i.eq(1)
#             for _ in range(128):
#                 yield Tick()

#             with open("out-zlp.bin", "rb") as f:
#                 for sample in iter(lambda: f.read(2), b""):
#                     yield Cat(dut.phy.pins.p.i, dut.phy.pins.n.i).eq(sample[0] & 0b11)
#                     yield Tick()

#             yield dut.phy.pins.p.i.eq(1)
#             for _ in range(512):
#                 yield Tick()




            # with open("in.bin", "rb") as f:
            #     for sample in iter(lambda: f.read(2), b""):
            #         yield Cat(dut.phy.pins.p.i, dut.phy.pins.n.i).eq(sample[0] & 0b11)
            #         yield Tick()

            # yield dut.phy.pins.p.i.eq(1)
            # for _ in range(2048):
            #     yield Tick()

        # def phy_rx_process():
        #     for line in args.sample:
        #         if line[0] == "#":
        #             continue
        #         rx_packet = line.split()

        #         yield from dut.phy.send(rx_packet)

        #         if rx_packet[0] == "69":
        #             print("-> IN:", " ".join(rx_packet))
        #         elif rx_packet[0] == "a5":
        #             print("-> SOF")
        #         elif rx_packet[0] == "d2":
        #             print("-> ACK")
        #         elif rx_packet[0] == "e1":
        #             print("-> OUT:", " ".join(rx_packet))
        #         elif rx_packet[0] == "2d":
        #             print("-> SETUP:", " ".join(rx_packet))
        #         elif rx_packet[0] == "4b":
        #             print("-> DATA1:", " ".join(rx_packet))
        #         elif rx_packet[0] == "c3":
        #             print("-> DATA0:", " ".join(rx_packet))
        #         else:
        #             print("-> (unknown PID: {})".format(rx_packet[0]))

        #         yield Tick()

        # def phy_tx_process():
        #     while True:
        #         tx_data = yield from dut.phy.receive()

        #         if tx_data[0] == 0xc3:
        #             print("<- DATA0:", " ".join("{:02x}".format(b) for b in tx_data))
        #         elif tx_data[0] == 0x4b:
        #             print("<- DATA1:", " ".join("{:02x}".format(b) for b in tx_data))
        #         elif tx_data[0] == 0x5a:
        #             print("<- NAK")
        #         elif tx_data[0] == 0xd2:
        #             print("<- ACK")
        #         else:
        #             print("<- (unknown PID: {:x})".format(tx_data[0]))

        #         yield Tick()

        # def rgb_read_process():
        #     yield dut.rgb_rp.ready.eq(1)
        #     rdata = []
        #     while True:
        #         if (yield dut.rgb_rp.valid):
        #             rdata.append((yield dut.rgb_rp.byte))
        #             if (yield dut.rgb_rp.last):
        #                 print("   [RGB endpoint received {} bytes. ({})]"
        #                       .format(len(rdata), " ".join("{:02x}".format(b) for b in rdata)))
        #                 rdata.clear()
        #         yield Tick()

        sim.add_clock(1e-6)
        sim.add_sync_process(phy_rx_process)
        # sim.add_sync_process(phy_tx_process)
        # sim.add_sync_process(rgb_read_process)
        sim.run()
