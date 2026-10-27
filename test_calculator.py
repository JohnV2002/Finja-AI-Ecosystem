from calculator import double

def test_positive():
    assert double(3) == 6

def test_zero():
    assert double(0) == 0
