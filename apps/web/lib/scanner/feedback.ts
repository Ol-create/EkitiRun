// Beep and vibrate after a scan, so volunteers don't need to look at the screen. Owner: Lead (E7).
let audio: AudioContext | null = null;

function tone(frequency: number, startAt: number, seconds: number) {
  if (!audio) return;
  const oscillator = audio.createOscillator();
  const gain = audio.createGain();
  oscillator.frequency.value = frequency;
  gain.gain.value = 0.2;
  oscillator.connect(gain).connect(audio.destination);
  oscillator.start(audio.currentTime + startAt);
  oscillator.stop(audio.currentTime + startAt + seconds);
}

/** Call from a tap (e.g. the login button): browsers only allow sound after a user gesture. */
export function unlockAudio() {
  audio ??= new AudioContext();
  void audio.resume();
}

/** good: one high beep and a short buzz. Otherwise two low beeps and a double buzz. */
export function signal(good: boolean) {
  if (good) {
    tone(1320, 0, 0.12);
    navigator.vibrate?.(120);
  } else {
    tone(330, 0, 0.15);
    tone(330, 0.22, 0.15);
    navigator.vibrate?.([100, 80, 100]);
  }
}
