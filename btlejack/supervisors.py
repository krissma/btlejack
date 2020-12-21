"""
Sniffing/Hijacking supervisors.

Supervisors are dedicated classes instrumenting an interface (single or multiple
sniffing devices) to:
- detect and list access addresses
- recover any connection core parameters (channel map, interval, increment) and
  follow the corresponding connection
- listen for connection requests and follow the corresponding connection
- jam any followed connection
- hijack any followed connection

Each supervisor implements a tiny state machine to keep track of the underlying
attacks and data.

You may want to implement your supervisor in order to follow a specific behavior
or simply interact with another user interface.
"""

from btlejack.jobs import SingleSnifferInterface, MultiSnifferInterface
from btlejack.session import BtlejackSession, BtlejackSessionError
from btlejack.packets import *
from btlejack.link import DeviceError


class Supervisor(object):
    """
    Default supervisor class.
    """

    def stop(self):
        pass

    def process_packets(self):
        packets = self.interface.read_packet()
        if (packets != []):
            # if (len(packets) == 8):
            print("packets in process_packets: ", packets)
        if len(packets) > 0:
            for pkt in packets:
                pkt = PacketRegistry.decode(pkt)
                self.on_packet_received(pkt)

    def on_packet_received(self, packet):
        if isinstance(packet, VerbosePacket):
            self.on_verbose(packet)
        elif isinstance(packet, DebugPacket):
            self.on_debug(packet)

    def send_packet(self, packet):
        """
        Send packet to the link.
        """
        self.interface.send_packet(packet)

    def on_ll_packet(self, packet):
        """
        Called when a BLE LL packet is captured.
        """
        pass

    def on_verbose(self, packet):
        """
        Called when a verbose packet is received from the sniffer.
        """
        print("In verbose")
        print('V:'+str(packet))

    def on_debug(self, packet):
        """
        Called when a debug packet is received from the sniffer.
        """
        print('D:'+str(packet))


class SendTestPacket(Supervisor):
    """
    Test packet supervisor. Allows to send a packet for testing.
    """

    def __init__(self, devices=None, baudrate=115200, channel=37):
        super().__init__()
        self.channel = channel

        # Pick first device as we only want to use one
        if devices is not None:
            # TODO Zugriff auf devices[0] machen?
            if len(devices) >= 1:
                self.interface = SingleSnifferInterface(devices[0], baudrate)
            else:
                raise DeviceError('No device provided')
        else:
            self.interface = SingleSnifferInterface()
            # print("SendTestPacketSupervisor")

    def send_test_packet(self, packet, channel):
        """
        Send a test packet.
        """
        self.interface.send_test_packet(packet, channel)

    def on_packet_received(self, packet):
        print("Overriding on_packet_received")
        super().on_packet_received(packet)


class ReceiveTestPacket(Supervisor):
    """
    copied from AdvertisementsSniffer supervisor without changes.

    This supervisor allow to configure the sniffer as a sniffer for advertisements, according to
     the provided policy. 
    """
    STATE_IDLE = 0
    STATE_SNIFFING = 1

    def __init__(self, devices=None, baudrate=115200, channel=37, policy={"policy_type": "blacklist", "rules": []}, accept_invalid_crc=False):
        super().__init__()
        self.channel = channel
        self.policy = policy
        self.accept_invalid_crc = accept_invalid_crc
        self.state = self.STATE_IDLE

        # Configure the devices.
        if devices is not None:
            self.interface = MultiSnifferInterface(
                len(devices), baudrate, devices)
        else:
            self.interface = MultiSnifferInterface(3)

        # Configure the filtering policy.
        self.interface.reset_filtering_policy(self.policy["policy_type"])
        for rule in self.policy["rules"]:
            self.interface.add_rule(
                rule["pattern"], rule["mask"], rule["position"])

        self.enable_adv_sniffing()

    def enable_adv_sniffing(self):
        # Enable advertisement sniffing.
        if self.interface.enable_advertisements_sniffing(self.channel):
            self.state = self.STATE_SNIFFING
        else:
            print("Error occured when attempted to put radio into sniffing mode")

    def disable_adv_sniffing(self):
        if self.interface.disable_advertisements_sniffing():
            self.state = self.STATE_IDLE
        else:
            print("Error occured when attempted to disable radios sniffing mode")

    def on_advertisements_response(self, packet):
        pass

    def on_packet_received(self, packet):
        """
        Dispatch received packets.
        """
        #print("In on_packet_received")
        if isinstance(packet, VerbosePacket) or isinstance(packet, DebugPacket):
            super().on_packet_received(packet)
        else:
            if isinstance(packet, AdvertisementsResponse):
                self.on_advertisements_response(packet)
            elif isinstance(packet, AdvertisementsPacketNotification):
                if self.state == self.STATE_SNIFFING:
                    # Checks if the CRC is valid or if the accept_invalid_crc option is set
                    if packet.crc_ok == 0x01 or (packet.crc_ok == 0x00 and self.accept_invalid_crc):
                        self.on_adv_packet(packet)


class AdvertisementsJammer(Supervisor):
    """
    Advertisements jammer supervisor.

    This supervisor allow to configure the sniffer as a reactive jammer for jamming advertisements, according to
     the provided pattern. 
    """

    def __init__(self, devices=None, baudrate=115200, channel=37, pattern=b"", position=0):
        super().__init__()
        self.channel = channel
        self.pattern = pattern
        self.position = position

        if devices is not None:
            self.interface = MultiSnifferInterface(
                len(devices), baudrate, devices)
        else:
            self.interface = MultiSnifferInterface(3)
        print("Calling enable_adv_jamming in _init in supervisors.py now")
        self.enable_adv_jamming(self.channel, self.pattern, self.position)

    def enable_adv_jamming(self, channel, pattern, position):
        self.interface.enable_advertisements_reactive_jamming(
            channel, pattern, position)

    def disable_adv_jamming(self):
        if(self.interface.disable_advertisements_reactive_jamming()):
            print("[!] Jamming could not be disabled")

    def on_adv_jammed(self):
        """
        This method is called when an advertisement is jammed.
        """
        pass

    def on_packet_received(self, packet):
        """
        Dispatch received packets.
        """
        if isinstance(packet, VerbosePacket):
            if(packet.data == b"ADV_JAMMED"):
                self.on_adv_jammed()
            else:
                self.on_verbose(packet)
        elif isinstance(packet, VerbosePacket) or isinstance(packet, DebugPacket):
            super().on_packet_received(packet)


class AdvertisementsSniffer(Supervisor):
    """
    Advertisements sniffer supervisor.

    This supervisor allow to configure the sniffer as a sniffer for advertisements, according to
     the provided policy. 
    """
    STATE_IDLE = 0
    STATE_SNIFFING = 1

    def __init__(self, devices=None, baudrate=115200, channel=37, policy={"policy_type": "blacklist", "rules": []}, accept_invalid_crc=False):
        super().__init__()
        self.channel = channel
        print("Advertisement channel sets channel to ", channel)
        self.policy = policy
        # TODO, change this back
        self.accept_invalid_crc = True
        #self.accept_invalid_crc = accept_invalid_crc
        self.state = self.STATE_IDLE

        # Configure the devices.
        if devices is not None:
            self.interface = MultiSnifferInterface(
                len(devices), baudrate, devices)
        else:
            # TODO: This should be 3, changed to 1 for testing reasons
            self.interface = MultiSnifferInterface(1)

        # Configure the filtering policy.
        self.interface.reset_filtering_policy(self.policy["policy_type"])
        for rule in self.policy["rules"]:
            self.interface.add_rule(
                rule["pattern"], rule["mask"], rule["position"])

        self.enable_adv_sniffing()

    def enable_adv_sniffing(self):
        # Enable advertisement sniffing.
        if self.interface.enable_advertisements_sniffing(self.channel):
            #print("In enable_adv_sniffing in supervisors.py")
            self.state = self.STATE_SNIFFING
        else:
            print("Error occured when attempted to put radio into sniffing mode")

    def disable_adv_sniffing(self):
        if self.interface.disable_advertisements_sniffing():
            self.state = self.STATE_IDLE
        else:
            print("Error occured when attempted to disable radios sniffing mode")

    def on_advertisements_response(self, packet):
        pass

    def on_packet_received(self, packet):
        """
        Dispatch received packets.
        """
        if isinstance(packet, VerbosePacket) or isinstance(packet, DebugPacket):
            super().on_packet_received(packet)
        else:
            if isinstance(packet, AdvertisementsResponse):
                self.on_advertisements_response(packet)
            elif isinstance(packet, AdvertisementsPacketNotification):
                if self.state == self.STATE_SNIFFING:
                    # Checks if the CRC is valid or if the accept_invalid_crc option is set
                    if packet.crc_ok == 0x01 or (packet.crc_ok == 0x00 and self.accept_invalid_crc):
                        self.on_adv_packet(packet)


class AccessAddressSniffer(Supervisor):
    """
    Access address sniffer.

    This supervisor configures the sniffing interface to detect BLE access
    addresses, their associated signal levels and number of packets received.

    Override the on_access_address() method if you want to process any detected
    access addresses.
    """

    def __init__(self, devices=None, baudrate=115200):
        super().__init__()

        # Pick first device as we don't need more
        if devices is not None:
            if len(devices) >= 1:
                self.interface = SingleSnifferInterface(devices[0], baudrate)
            else:
                raise DeviceError('No device provided')
        else:
            self.interface = SingleSnifferInterface()

        # send packet
        self.interface.send_test_packet()

    def on_packet_received(self, packet):
        """
        Dispatch received packets.
        """
        if isinstance(packet, VerbosePacket) or isinstance(packet, DebugPacket):
            super().on_packet_received(packet)
        else:
            if isinstance(packet, AccessAddressNotification):
                if packet.access_address not in self.aad:
                    self.aad[packet.access_address] = 1
                else:
                    self.aad[packet.access_address] += 1
                self.on_access_address(
                    packet.access_address,
                    packet.rssi,
                    self.aad[packet.access_address]
                )

    def on_access_address(self, address, rssi, nb_packets):
        """
        Access address callback.

        This method is called every time an access address is detected or updated.
        """
        print(
            '[ -%3d dBm] 0x%08x | pkts: %d' % (
                rssi,
                address,
                nb_packets
            )
        )


class ConnectionRecovery(Supervisor):
    """
    Existing connection recovery supervisor.

    This supervisor drives the sniffing interface to recover an existing
    connection parameters, and then allows to jam and hijack on the fly.
    """

    STATE_IDLE = 0
    STATE_RECOVER_CRC = 1
    STATE_RECOVER_CHM = 2
    STATE_RECOVER_HOPINTER = 3
    STATE_RECOVER_HOPINC = 4
    STATE_FOLLOWING = 5
    STATE_HIJACKING = 6
    STATE_HIJACKED = 7
    STATE_RECOVER_CCHM = 8

    def __init__(self, access_address, channel_map=None, hop_interval=None, crc=None, devices=None, baudrate=115200, timeout=0):
        super().__init__()

        # Retrieve the user session
        try:
            self.session = BtlejackSession.get_instance()
        except BtlejackSessionError as session_error:
            # something went wrong, wont keep the session
            self.session = None

        if devices is not None:
            self.interface = MultiSnifferInterface(
                len(devices), baudrate, devices)
        else:
            self.interface = MultiSnifferInterface(999)
        self.state = self.STATE_RECOVER_CRC
        self.chm_provided = (channel_map is not None)
        self.crc_provide = (crc is not None)
        self.hop_provided = (hop_interval is not None)
        self.access_address = access_address
        self.hop_interval = hop_interval
        self.chm = channel_map
        self.packet_sent = False
        self.crc = crc
        self.cchm_notifications = 0
        self.cchm = 0
        self.timeout = timeout

        # Launch recovery based on the provided informations.
        if self.crc is not None:

            # Save CRC in session if possible
            if self.session is not None:
                self.session.add_connection(
                    self.access_address,
                    {'crcinit': self.crc}
                )
                self.session.save()

            if self.chm is not None:
                self.state = self.STATE_RECOVER_HOPINTER
                self.interface.recover_hop(access_address, self.crc, self.chm)
            else:
                self.state = self.STATE_RECOVER_CCHM
                self.interface.recover_chm(
                    access_address, self.crc, self.timeout)
        else:
            self.state = self.STATE_RECOVER_CRC
            self.interface.recover_crcinit(access_address)

    def jam(self):
        """
        Enable jamming.
        """
        if self.state == self.STATE_FOLLOWING:
            self.interface.enable_jamming(True)

    def hijack(self):
        """
        Enable hijacking
        """
        if self.state == self.STATE_FOLLOWING:
            self.state = self.STATE_HIJACKING
            self.interface.enable_hijacking(True)

    def on_packet_received(self, packet):
        """
        Packet handler.
        """
        # print(packet)
        if isinstance(packet, VerbosePacket) or isinstance(packet, DebugPacket):
            super().on_packet_received(packet)
        elif isinstance(packet, ConnectionLostNotification):
            self.on_connection_lost()
        else:
            if self.state == self.STATE_RECOVER_CRC:
                if isinstance(packet, CrcNotification):
                    # Forward CRC
                    self.on_crc(packet.crc)
                    self.crc = packet.crc

                    # Save CRC in session if possible
                    if self.session is not None:
                        self.session.add_connection(
                            self.access_address,
                            {'crcinit': self.crc}
                        )
                        self.session.save()

                    # If channel map is provided
                    if self.chm_provided:
                        # self.on_chm(self.chm)
                        self.state = self.STATE_RECOVER_HOPINTER
                    else:
                        # We are going to recover the channel map
                        # but in a collaborative way if we have
                        # many interfaces available.
                        if self.interface.get_nb_interfaces() >= 1:
                            # If more than one interface, it is more
                            # efficient to do a collaborative chm recovery
                            self.state = self.STATE_RECOVER_CCHM

                            # we reset all the interfaces
                            self.interface.reset()
                            self.cchm_notifications = 0
                            self.cchm = 0

                            # and ask for a collaborative channel mapping
                            self.interface.recover_chm(
                                self.access_address,
                                self.crc,
                                self.timeout
                            )
                        else:
                            # otherwise, we continue with the 'normal' way
                            self.state = self.STATE_RECOVER_CHM

            elif self.state == self.STATE_RECOVER_CHM:
                if isinstance(packet, ChannelMapNotification):
                    self.on_chm(packet.channel_map)

                    if self.hop_provided:
                        self.state = self.STATE_RECOVER_HOPINC
                    else:
                        self.state = self.STATE_RECOVER_HOPINTER
            elif self.state == self.STATE_RECOVER_CCHM:
                if isinstance(packet, ChannelMapNotification):
                    # we expect to get as many chm notification as interfaces
                    self.cchm |= packet.channel_map
                    self.cchm_notifications += 1
                    if self.cchm_notifications == self.interface.get_nb_interfaces():
                        self.state = self.STATE_RECOVER_HOPINTER
                        self.on_chm(self.cchm)
            elif self.state == self.STATE_RECOVER_HOPINTER:
                if isinstance(packet, HopIntervalNotification):
                    # Save CHM too in session if possible
                    self.on_hopinterval(packet.interval)
                    self.state = self.STATE_RECOVER_HOPINC
            elif self.state == self.STATE_RECOVER_HOPINC:
                if isinstance(packet, HopIncrementNotification):
                    self.state = self.STATE_FOLLOWING
                    self.on_hopincrement(packet.increment)
            elif self.state == self.STATE_FOLLOWING:
                self.on_ll_packet(packet)
            elif self.state == self.STATE_HIJACKING:
                if isinstance(packet, HijackStatusNotification):
                    if packet.status:
                        self.state = self.STATE_HIJACKED
                        self.on_hijacking_success()
                    else:
                        self.state = self.STATE_IDLE
                        self.on_hijacking_failed()
            elif self.state == self.STATE_HIJACKED:
                if isinstance(packet, SendPacketResponse):
                    self.sent_packet = False
                else:
                    self.on_ll_packet(packet)

    def on_crc(self, crc):
        """
        Connection CRC has been recovered.
        """
        print('CRC: %06x' % crc)

    def on_chm(self, chm):
        """
        Channel map has been recovered.
        """
        print('sup:on_chm')
        print('CHM: %010x' % chm)
        self.state = self.STATE_RECOVER_HOPINTER
        self.chm = chm
        self.recover_hop(
            self.access_address,
            self.crc,
            self.chm
        )

    def on_hopinterval(self, interval):
        """
        Hop interval has been recovered.
        """
        print('Interval: %d' % interval)

    def on_hopincrement(self, increment):
        """
        Hop increment has been recovered.
        """
        print('Increment: %d' % increment)

    def on_ll_packet(self, packet):
        """
        A BLE LL packet has been captured.
        """
        print(packet)

    def on_hijacking_success(self):
        """
        Hijacking was successful, hijacker now owns this connection.
        """
        pass

    def on_hijacking_failed(self):
        """
        Could not hijack this connection.
        """
        pass

    def on_connection_lost(self):
        """
        Connection has been lost.
        """
        pass

    def send_packet(self, packet):
        """
        Send a BLE LL packet.
        """
        self.packet_sent = self.interface.send_packet(packet)


class ConnectionSniffer(Supervisor):
    """
    Multiple channels connection sniffing supervisor.

    This supervisor drive the sniffing interface to sniff for new BLE
    connections, and allows to jam and hijack them on the fly.
    """

    STATE_IDLE = 0
    STATE_SYNCING = 1
    STATE_FOLLOWING = 2
    STATE_HIJACKING = 3
    STATE_HIJACKED = 4

    def __init__(self, bd_address='ff:ff:ff:ff:ff:ff', devices=None):
        super().__init__()
        self.interface = MultiSnifferInterface(3, devices=devices)
        self.bd_address = bd_address

        self.sniff()

        # Retrieve the user session
        try:
            self.session = BtlejackSession.get_instance()
        except BtlejackSessionError as session_error:
            # something went wrong, wont keep the session
            self.session = None

    def sniff(self):
        """
        Start sniffing for new connections.
        """
        self.interface.sniff_connection(
            self.bd_address
        )
        self.state = self.STATE_SYNCING
        self.access_address = None
        self.sent_packet = False

    def jam(self):
        """
        Enable jamming.
        """
        if self.state == self.STATE_FOLLOWING:
            self.interface.enable_jamming(True)

    def hijack(self):
        """
        Enable hijacking
        """
        if self.state == self.STATE_FOLLOWING:
            self.state = self.STATE_HIJACKING
            self.interface.enable_hijacking(True)

    def process_packets(self):
        packets = self.interface.read_packet()
        if len(packets) > 0:
            for pkt in packets:
                pkt = PacketRegistry.decode(pkt)
                self.on_packet_received(pkt)

    def on_packet_received(self, packet):
        """
        Packet handler.
        """
        if isinstance(packet, VerbosePacket) or isinstance(packet, DebugPacket):
            super().on_packet_received(packet)
        elif isinstance(packet, ConnectionLostNotification):
            self.on_connection_lost()
        else:
            if self.state == self.STATE_SYNCING:
                if isinstance(packet, ConnectionRequestNotification):
                    # Rebuild connection packet
                    class rawpacket:
                        def __init__(self, payload):
                            self.data = payload
                    pkt = bytes([0]*10) + bytes([0x05, 0x22]) + \
                        packet.inita + packet.adva+packet.payload
                    self.access_address = 0x8e89bed6
                    self.on_ll_packet(rawpacket(pkt))

                    # Save connection parameters
                    if self.session is not None:
                        self.session.add_connection(
                            packet.access_address,
                            {
                                'crcinit': packet.crc_init
                            }
                        )
                        self.session.save()

                    self.access_address = packet.access_address
                    self.on_connection(
                        packet.inita,
                        packet.adva,
                        packet.crc_init,
                        packet.hop_interval,
                        packet.hop_increment,
                        packet.channel_map,
                        packet.timeout
                    )
                    self.state = self.STATE_FOLLOWING
            elif self.state == self.STATE_FOLLOWING:
                self.on_ll_packet(packet)
            elif self.state == self.STATE_HIJACKING:
                if isinstance(packet, HijackStatusNotification):
                    if packet.status:
                        self.state = self.STATE_HIJACKED
                        self.on_hijacking_success()
                    else:
                        self.state = self.STATE_IDLE
                        self.on_hijacking_failed()
            elif self.state == self.STATE_HIJACKED:
                if isinstance(packet, SendPacketResponse):
                    self.sent_packet = False
                else:
                    self.on_ll_packet(packet)

    def on_connection(self, inita, adva, crc_init, interval, increment, channel_map):
        print('Got connection !')

    def on_ll_packet(self, packet):
        """
        A BLE LL packet has been captured.
        """
        print(packet)

    def on_hijacking_success(self):
        """
        Hijacking was successful, hijacker now owns this connection.
        """
        pass

    def on_hijacking_failed(self):
        """
        Could not hijack this connection.
        """
        pass

    def on_connection_lost(self):
        """
        Connection has been lost.
        """
        pass

    def send_packet(self, packet):
        """
        Send a BLE LL packet.
        """
        self.packet_sent = self.interface.send_packet(packet)
