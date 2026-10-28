from app.models.inverter_state import InverterState
import time

CONFIRMATION_SECONDS = 180


class GridMonitor:
    def __init__(self, path=None):
        self.grid_available = False
        self.confirmed = None
        self.candidate = None
        self.since = None
        self.last_valid = None
        self.confirmed_at = None
        self.path = path
        self.transitions = []
        self.raw_previous = None
        self.saved_episode = None
        self.episode_persisted = False
        if path:
            try:
                import json
                from pathlib import Path
                saved = json.loads(Path(path).read_text(encoding='utf-8'))
                if not isinstance(saved,dict):
                    saved={}
                self.transitions = [v for v in saved.get('transitions', [])
                    if type(v) in (int, float) and 0 <= time.time()-v <= 600][-100:]
                episode=saved.get('episode') or {}
                if not isinstance(episode,dict):
                    episode={}
                if (type(episode.get('online')) is bool
                        and type(episode.get('at')) in (int,float)
                        and 0 < episode['at'] <= time.time()):
                    self.saved_episode=dict(online=episode['online'],at=episode['at'])
                    self.episode_persisted=True
            except (OSError, ValueError, TypeError):
                pass

    def handle_inverter_state(self, state: InverterState):
        if not state.valid:
            self.candidate = None
            self.since = None
            self.raw_previous = None
            return

        now = time.monotonic()
        if self.last_valid is not None and now - self.last_valid > 30:
            self.candidate = None
            self.since = None
            self.raw_previous = None
        self.last_valid = now
        self.grid_available = state.grid_available
        wall = time.time()
        self.transitions = [v for v in self.transitions if 0 <= wall-v <= 600]
        if self.raw_previous is not None and self.raw_previous != state.grid_available:
            self.transitions.append(wall)
            self.transitions = self.transitions[-100:]
            if self.path:
                from app.utils.json_store import atomic_write_json
                try:
                    atomic_write_json(self.path, {'transitions': self.transitions,'episode':self.saved_episode})
                    self.episode_persisted=self.saved_episode is not None
                except OSError:
                    from app.utils.logger import log
                    log('Grid instability journal unavailable; current observations remain in memory')
        self.raw_previous = state.grid_available
        if state.grid_available == self.confirmed:
            self.candidate = None
            self.since = None
        elif self.candidate != state.grid_available:
            self.candidate = state.grid_available
            self.since = now
        elif now - self.since >= CONFIRMATION_SECONDS:
            self.confirmed = state.grid_available
            # Requalification still takes 180 seconds after restart. Reuse the
            # durable episode only when the confirmed state is unchanged, so
            # restarting EH does not grant another Eco retry budget.
            same_episode=self.episode_persisted and self.saved_episode and self.saved_episode['online']==self.confirmed
            self.confirmed_at = (self.saved_episode['at'] if same_episode
                                 else time.time()-(now-self.since))
            self.saved_episode=dict(online=self.confirmed,at=self.confirmed_at)
            self.episode_persisted=bool(same_episode)
            if self.path:
                from app.utils.json_store import atomic_write_json
                try:
                    atomic_write_json(self.path,{'transitions':self.transitions,'episode':self.saved_episode})
                    self.episode_persisted=True
                except OSError:
                    from app.utils.logger import log
                    log('Grid episode persistence failed; restart continuity is unconfirmed')
            self.candidate = None
            self.since = None

    def publish(self, client, valid):
        import json
        client.publish('energyhub/grid/confirmed/attributes',json.dumps({
            'transition_at':self.confirmed_at, 'raw_transitions_10m':len(self.transitions),
            'episode_persisted':self.episode_persisted and self.confirmed is not None,
            'confirmation_seconds':CONFIRMATION_SECONDS,
            'transition_pending':self.candidate is not None,
            'last_raw_transition_at':self.transitions[-1] if self.transitions else None,
            'unstable':len(self.transitions)>=4, 'checked_at':time.time()}),retain=True)
        client.publish('energyhub/grid/confirmed',
                       'ON' if self.confirmed is True else 'OFF' if self.confirmed is False else 'unknown',
                       retain=True)
        client.publish('energyhub/grid/confirmed/availability',
                       'online' if valid and self.confirmed is not None else 'offline', retain=True)

    @property
    def is_available(self):
        return self.grid_available
