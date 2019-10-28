from nmigen import *
from nmigen.utils import log2_int

from ...lib import stream
from ...protocol import LineState


# __all__ = ["NRZIDecoder", "USBPHYRX"]
__all__ = ["NRZIDecoder2", "NRZIDecoder", "USBPHYRX"]


class NRZIDecoder(Elaboratable):
    def __init__(self, period):
        self.period = period
        self.din    = Signal(2)
        self.source = stream.Endpoint([("data", 8)])
        self.idle   = Signal()
        # self.enable = Signal()

    def elaborate(self, platform):
        m = Module()

        half_period = self.period // 2

        phase  = Signal(range(8*self.period+1))

        shreg = Signal(15)
        offset = Signal(3)
        width = Signal(3)
        bitstuff = Signal()

        valid = Signal()

        # with m.If(self.enable):
        din_r = Signal.like(self.din)
        m.d.sync += din_r.eq(self.din)

        m.d.sync += self.source.valid.eq(0)

        with m.If(self.din == din_r):
            with m.If(phase < 8*self.period):
                m.d.sync += phase.eq(phase + 1)
            with m.Else():
                m.d.comb += self.idle.eq(1)
                m.d.sync += offset.eq(0)

        with m.Elif(phase >= half_period):
            m.d.sync += bitstuff.eq(0)
            for i in range(7):
                with m.If((phase >= half_period + i*self.period) & (phase < half_period + (i+1)*self.period)):
                    if i == 6:
                        m.d.sync += bitstuff.eq(1)
                    with m.If(bitstuff):
                        m.d.sync += shreg.eq(Cat(Repl(0b1, i), shreg))
                        m.d.comb += width.eq(C(i))
                    with m.Else():
                        m.d.sync += shreg.eq(Cat(Repl(0b1, i), C(0b0), shreg))
                        m.d.comb += width.eq(C(i + 1))
            m.d.sync += [
                phase.eq(1),
                Cat(offset, valid).eq(offset + width),
                self.source.valid.eq(valid),
                self.source.data.eq(shreg.bit_select(offset, width=8)[::-1]),
                self.source.last.eq(Mux(bitstuff, self.din, din_r) == LineState.SE0),
            ]

        with m.If(self.source.valid & self.source.last):
            m.d.sync += phase.eq(8*self.period)

        return m


class NRZIDecoder2(Elaboratable):
    """
    if the ctr_phase == period, shift a 1 in the shreg,
    every time din != din_r, update the shreg offset with the number of period elapsed.
    """
    def __init__(self, period):
        self.period = period

        self.din    = Signal(2)
        self.idle   = Signal()
        self.source = stream.Endpoint([("data", 8)])

    def elaborate(self, platform):
        m = Module()

        din_r = Signal.like(self.din)
        m.d.sync += din_r.eq(self.din)

        dout_shreg    = Signal(8 + 7)
        dout_offset   = Signal(log2_int(8))
        dout_valid    = Signal()
        dout_bitstuff = Signal()

        m.d.comb += dout_bitstuff.eq(dout_shreg[:6].all())

        ctr_stable = Signal(range(self.period), reset=self.period - 1)

        with m.If(self.din == din_r):
            with m.If(ctr_stable != 0):
                m.d.sync += ctr_stable.eq(ctr_stable - 1)
            with m.Elif(~dout_bitstuff):
                m.d.sync += ctr_stable.eq(ctr_stable.reset)
                m.d.sync += [
                    dout_shreg.eq(Cat(C(1), dout_shreg)),
                    Cat(dout_offset, dout_valid).eq(dout_offset + 1)
                ]
            with m.Else():
                # Assume we are in between two packets.
                m.d.comb += self.idle.eq(1)
                m.d.sync += dout_offset.eq(0)
        with m.Elif(ctr_stable < int(self.period // 2)):
            m.d.sync += ctr_stable.eq(ctr_stable.reset - 1)
            m.d.sync += dout_shreg.eq(Cat(C(0), dout_shreg))
            with m.If(~dout_bitstuff):
                m.d.sync += Cat(dout_offset, dout_valid).eq(dout_offset + 1)

        m.d.sync += [
            self.source.valid.eq(dout_valid),
            self.source.data.eq(dout_shreg.bit_select(dout_offset, width=8)[::-1]),
            self.source.last.eq(Mux(dout_bitstuff, self.din, din_r) == LineState.SE0)
        ]

        return m


class USBPHYRX(Elaboratable):
    def __init__(self, sync_freq):
        self.sync_freq = sync_freq
        self.din       = Signal(2)
        self.source    = stream.Endpoint([("data", 8)])
        self.idle      = Signal()
        self.enable    = Signal()

    def elaborate(self, platform):
        m = Module()

        period = int(self.sync_freq//12e6)
        ctr_se0 = Signal(range(2*period))

        nrzi_dec = m.submodules.nrzi_dec = EnableInserter(self.enable)(NRZIDecoder(period))
        m.d.comb += [
            nrzi_dec.din.eq(self.din),
            self.idle.eq(nrzi_dec.idle),
        ]

        with m.FSM() as fsm:
            with m.State("IDLE"):
                with m.If(nrzi_dec.source.valid & (nrzi_dec.source.data == C(0b10000000))):
                    # A SYNC pattern has been detected, which signals the start of a packet.
                    m.next = "RECEIVE"

            with m.State("RECEIVE"):
                m.d.comb += nrzi_dec.source.connect(self.source)
                with m.If(nrzi_dec.source.valid & nrzi_dec.source.last & nrzi_dec.source.ready):
                    m.next = "IDLE"

        return m
