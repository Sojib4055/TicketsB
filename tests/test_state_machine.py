from src.state_machine import AgentState, StateMachine


def test_transition():
    sm = StateMachine()
    sm.transition(AgentState.AVAILABILITY_DETECTED)
    assert sm.state == AgentState.AVAILABILITY_DETECTED
