class TimeSession(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    store = models.ForeignKey(Store, on_delete=models.CASCADE)
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    in_range = models.BooleanField(default=True)  # True=work, False=away
    seconds = models.IntegerField(default=0)

    @property
    def is_open(self): return self.ended_at is None


