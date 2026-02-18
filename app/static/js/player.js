document.addEventListener('DOMContentLoaded', () => {
    const audioPlayer = document.getElementById('audioPlayer');
    const playBtn = document.getElementById('playBtn');
    const voiceSelect = document.getElementById('voiceSelect');
    const speedRange = document.getElementById('speedRange');
    const pitchRange = document.getElementById('pitchRange');
    const textContent = document.getElementById('textContent'); // The raw text container
    const exportBtn = document.getElementById('exportBtn');
    const exportStatus = document.getElementById('exportStatus');

    let isPlaying = false;

    // Helper to get params
    function getParams() {
        const speed = parseFloat(speedRange.value);
        // EdgeTTS uses percentage for rate: +50%, -20%
        let rateStr = (speed >= 1.0) ? `+${Math.round((speed - 1) * 100)}%` : `${Math.round((speed - 1) * 100)}%`;
        if (speed === 1.0) rateStr = "+0%";

        const pitch = parseInt(pitchRange.value);
        let pitchStr = (pitch >= 0) ? `+${pitch}Hz` : `${pitch}Hz`;

        return {
            voice: voiceSelect.value,
            rate: rateStr,
            pitch: pitchStr,
            text: textContent.innerText // Send all text for now
        };
    }

    // Update UI labels
    speedRange.addEventListener('input', (e) => {
        document.getElementById('speedValue').textContent = e.target.value + 'x';
    });
    pitchRange.addEventListener('input', (e) => {
        document.getElementById('pitchValue').textContent = e.target.value + 'Hz';
    });

    playBtn.addEventListener('click', async () => {
        if (isPlaying) {
            audioPlayer.pause();
            playBtn.innerText = 'Play';
            isPlaying = false;
        } else {
            // Start playing
            const params = getParams();
            // Construct URL
            // Note: Sending huge text in GET param is bad. Should normally be POST or handle differently.
            // Edge case: Text too long for URL.
            // WORKAROUND: For this demo, let's limit the text sent or use a POST -> Blob approach.
            // Or simpler: The backend stream endpoint handles GET.

            // Let's truncate for the GET request safety in this MVP
            const safeText = encodeURIComponent(params.text.substring(0, 1000)); // Limit first 1000 chars

            const url = `/api/tts/stream?text=${safeText}&voice=${params.voice}&rate=${params.rate}&pitch=${params.pitch}`;

            audioPlayer.src = url;
            audioPlayer.play();
            playBtn.innerText = 'Pause';
            isPlaying = true;
        }
    });

    audioPlayer.addEventListener('ended', () => {
        isPlaying = false;
        playBtn.innerText = 'Play';
    });

    // Export Logic
    exportBtn.addEventListener('click', async () => {
        const params = getParams();
        exportStatus.innerText = "Exporting... please wait.";

        const formData = new FormData();
        formData.append('text', params.text);
        formData.append('voice', params.voice);
        formData.append('rate', params.rate);
        formData.append('title', 'My_Audiobook'); // Could grab from H2

        try {
            const res = await fetch('/api/export', {
                method: 'POST',
                body: formData
            });
            const data = await res.json();
            if (data.status === 'completed') {
                exportStatus.innerHTML = `<a href="${data.download_url}" target="_blank">Download MP3</a>`;
            }
        } catch (e) {
            exportStatus.innerText = "Error exporting.";
        }
    });
});
