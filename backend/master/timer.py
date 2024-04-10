# From: https://stackoverflow.com/questions/56167390/resettable-timer-object-implementation-python
from threading import Timer
import time

class ResettableTimer(object):
    def __init__(self, interval, function, docID):
        self.interval = interval
        self.function = function
        self.docID = docID
        self.timer = Timer(self.interval, self.function, [self.docID])

    def run(self):
        self.timer.start()

    def reset(self):
        self.timer.cancel()
        self.timer = Timer(self.interval, self.function, [self.docID])
        self.timer.start()


if __name__ == '__main__':
    t = time.time()
    tim = ResettableTimer(5, lambda: print("Time's Up! Took ", time.time() - t, "seconds"))
    time.sleep(3)
    tim.reset()