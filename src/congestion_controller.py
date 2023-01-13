from enum import Enum


class CongestionState(Enum):
    SLOW_START = 0
    CONGESTION_AVOIDANCE = 1
    FAST_RECOVERY = 2

    def __str__(self) -> str:
        return self.__dict__.__str__()


class CongestionController:
    def __str__(self) -> str:
        return self.__dict__.__str__()

    """
    作为sender的时候，自己控制自己的拥塞窗口。
    """

    def __init__(self, init_cwnd=1, init_ssthresh=64) -> None:
        self.congestion_window: float = init_cwnd
        self.slow_thresh: float = init_ssthresh

        self.state = CongestionState.SLOW_START
        self.duplicate_ack_count = 0

    def cwnd(self) -> int:
        return int(self.congestion_window)

    def notify_timeout(self):
        def restart():
            self.slow_thresh = max(self.congestion_window / 2, 2)
            self.congestion_window = 1
            self.duplicate_ack_count = 0

        if self.state == CongestionState.SLOW_START:
            # 慢启动状态下timeout，我们需要阻止继续指数增长，重新开始，因为已经导致拥塞了
            restart()
        elif self.state == CongestionState.CONGESTION_AVOIDANCE:
            # 拥塞避免状态本来一直在线性增加，突然出现了timeout，说明网络出现了拥塞，需要重新开始。
            restart()
            self.state = CongestionState.SLOW_START  # 回到慢启动状态
        elif self.state == CongestionState.FAST_RECOVERY:
            restart()
            self.state = CongestionState.SLOW_START  # 回到慢启动状态

    def notify_duplicate(self):
        def dup_ack():
            # 慢启动状态下dupACK，counter+1
            if self.duplicate_ack_count < 3:
                self.duplicate_ack_count += 1
            else:
                # 若counter>=3，进入快速回复
                self.slow_thresh = max(self.congestion_window / 2, 2)
                self.congestion_window = self.slow_thresh + 3
                self.state = CongestionState.FAST_RECOVERY

        if self.state == CongestionState.SLOW_START:
            # 慢启动状态下dupACK，counter+1
            # 若counter==3，进入快速回复
            dup_ack()
        elif self.state == CongestionState.CONGESTION_AVOIDANCE:
            # 慢启动状态下dupACK，counter+1
            # 若counter==3，进入快速回复
            dup_ack()
        elif self.state == CongestionState.FAST_RECOVERY:
            # 窗口增加1
            self.congestion_window += 1

    def notify_new_ack(self):
        if self.state == CongestionState.SLOW_START:
            # 扩大窗口，counter清零
            self.congestion_window += 1
            self.duplicate_ack_count = 0
            self.check_cwnd_over_ssthresh()

        elif self.state == CongestionState.FAST_RECOVERY:
            # 扩大窗口，counter清零
            # 窗口遵循线性扩大
            self.congestion_window = self.slow_thresh
            self.duplicate_ack_count = 0
            self.state = CongestionState.CONGESTION_AVOIDANCE

        elif self.state == CongestionState.CONGESTION_AVOIDANCE:
            # 扩大窗口，counter清零
            self.congestion_window += (1.0 / self.congestion_window)
            self.duplicate_ack_count = 0

    def check_cwnd_over_ssthresh(self):
        # 内部事件，用来检查窗口是否超过了慢启动阈值
        if self.congestion_window < self.slow_thresh: return
        if self.state == CongestionState.SLOW_START:
            # 慢启动下，超过阈值表明，我们现在大概是上一次超时的阈值的一半，如果我们继续指数增长，马上就要超时了。
            # 所以，我们进入拥塞避免状态，开始线性增长
            self.state = CongestionState.CONGESTION_AVOIDANCE
        elif self.state == CongestionState.CONGESTION_AVOIDANCE:
            # 这很正常，你进入拥塞避免状态就是因为你超过了阈值。
            # LOGGER.warning("ssthresh是慢启动的阈值，其他状态下不用检查它。")
            pass
        elif self.state == CongestionState.FAST_RECOVERY:
            # 这很正常，你进入快速恢复状态的时候cwmd = ssthresh + 3，所以一定是大于ssthresh的。
            # LOGGER.warning("ssthresh是慢启动的阈值，其他状态下不用检查它。")
            pass
