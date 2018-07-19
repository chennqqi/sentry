import logging
from collections import defaultdict, namedtuple

logger = logging.getLogger(__name__)


Offsets = namedtuple('Offsets', 'local remote')


class InvalidState(Exception):
    pass


class InvalidStateTransition(Exception):
    pass


class MessageNotReady(Exception):
    pass


class PartitionState:
    # The ``SYNCHRONIZED`` state represents that the local offset is equal to
    # the remote offset. The local consumer should be paused to avoid advancing
    # further beyond the remote consumer.
    SYNCHRONIZED = 'SYNCHRONIZED'

    # The ``LOCAL_BEHIND`` state represents that the remote offset is greater
    # than the local offset. The local consumer should be unpaused to avoid
    # falling behind the remote consumer.
    LOCAL_BEHIND = 'LOCAL_BEHIND'

    # The ``REMOTE_BEHIND`` state represents that the local offset is greater
    # than the remote offset. The local consumer should be paused to avoid
    # advancing further beyond the remote consumer.
    REMOTE_BEHIND = 'REMOTE_BEHIND'

    # The ``UNKNOWN`` state represents that we haven't received enough data to
    # know the current offset state.
    UNKNOWN = 'UNKNOWN'


class SynchronizedPartitionStateManager(object):

    transitions = {  # from state -> set(to states)
        None: frozenset([
            PartitionState.UNKNOWN,
        ]),
        PartitionState.UNKNOWN: frozenset([
            PartitionState.LOCAL_BEHIND,
            PartitionState.REMOTE_BEHIND,
            PartitionState.SYNCHRONIZED,
        ]),
        PartitionState.REMOTE_BEHIND: frozenset([
            PartitionState.LOCAL_BEHIND,
            PartitionState.SYNCHRONIZED,
        ]),
        PartitionState.LOCAL_BEHIND: frozenset([
            PartitionState.SYNCHRONIZED,
            PartitionState.REMOTE_BEHIND,
        ]),
        PartitionState.SYNCHRONIZED: frozenset([
            PartitionState.LOCAL_BEHIND,
            PartitionState.REMOTE_BEHIND,
        ]),
    }

    def __init__(self, callback):
        self.partitions = defaultdict(lambda: (None, Offsets(None, None)))
        self.callback = callback

    def get_state_from_offsets(self, offsets):
        if offsets.local is None or offsets.remote is None:
            return PartitionState.UNKNOWN
        else:
            if offsets.local < offsets.remote:
                return PartitionState.LOCAL_BEHIND
            elif offsets.remote > offsets.local:
                return PartitionState.REMOTE_BEHIND
            else:  # local == remote
                return PartitionState.SYNCHRONIZED

    def set_local_offset(self, topic, partition, local_offset):
        previous_state, previous_offsets = self.partitions[(topic, partition)]
        if local_offset < previous_offsets.local:
            logger.info('Local offset has moved backwards (current: %s, previous: %s)', local_offset, previous_offsets.local)
        if previous_offsets.remote is not None and local_offset > previous_offsets.remote:
            logger.warning('Current local offset (%s) exceeds remote offset (%s)!', local_offset, previous_offsets.remote)
        updated_offsets = Offsets(local_offset, previous_offsets.remote)
        updated_state = self.get_state_from_offsets(updated_offsets)
        if previous_state is not updated_state and updated_state not in self.transitions[previous_state]:
            raise InvalidStateTransition('Unexpected state transition from {} to {}'.format(previous_state, updated_state))
        self.partitions[(topic, partition)] = (updated_state, updated_offsets)
        if previous_state is not updated_state:
            self.callback(
                topic,
                partition,
                (previous_state, previous_offsets),
                (updated_state, updated_offsets),
            )

    def set_remote_offset(self, topic, partition, remote_offset):
        previous_state, previous_offsets = self.partitions[(topic, partition)]
        if remote_offset < previous_offsets.remote:
            logger.info('Remote offset has moved backwards (current: %s, previous: %s)', remote_offset, previous_offsets.remote)
        updated_offsets = Offsets(previous_offsets.local, remote_offset)
        updated_state = self.get_state_from_offsets(updated_offsets)
        if previous_state is not updated_state and updated_state not in self.transitions[previous_state]:
            raise InvalidStateTransition('Unexpected state transition from {} to {}'.format(previous_state, updated_state))
        self.partitions[(topic, partition)] = (updated_state, updated_offsets)
        if previous_state is not updated_state:
            self.callback(
                topic,
                partition,
                (previous_state, previous_offsets),
                (updated_state, updated_offsets),
            )

    def validate_local_message(self, topic, partition, offset):
        state, offsets = self.partitions[(topic, partition)]
        if state is not PartitionState.LOCAL_BEHIND:
            raise InvalidState('Received a message while consumer is not in LOCAL_BEHIND state!')
        if offset >= offsets.remote:
            raise MessageNotReady('Received a message that has not been committed by remote consumer')
        if offset < offsets.local:
            logger.warning('Received a message prior to local offset (local consumer offset rewound without update?)')
