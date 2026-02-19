class Candle:
    def __init__(self):
        self.open = None
        self.high = None
        self.low = None
        self.close = None
        self.volume = 0.0

    def update(self, price, volume=0):
        if self.open is None:
            self.open = price
            self.high = price
            self.low = price
            self.close = price
            self.volume = volume
        else:
            self.high = max(self.high, price)
            self.low = min(self.low, price)
            self.close = price
            self.volume += volume

    def as_dict(self):
        return dict(open=self.open, high=self.high, low=self.low, close=self.close, volume=self.volume)

    def reset(self):
        self.open = self.high = self.low = self.close = None
        self.volume = 0.0
