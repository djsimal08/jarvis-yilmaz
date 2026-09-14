from agent.providers import pcm_to_wav


def test_pcm_is_wrapped_as_wav():
    data = pcm_to_wav(b"\x00\x00" * 100)
    assert data[:4] == b"RIFF"
    assert b"WAVE" in data[:16]
