import ffmpeg
import os
from typing import Optional

class AudioExporter:
    """
    Service to handle audio file conversion and metadata tagging.
    Requires FFmpeg to be installed on the system.
    """
    
    @staticmethod
    def convert_and_tag(input_path: str, output_path: str, bitrate: str = "128k", 
                        title: Optional[str] = None, artist: Optional[str] = None):
        """
        Converts input audio to MP3 with specified bitrate and metadata.
        """
        try:
            stream = ffmpeg.input(input_path)
            
            kwargs = {'audio_bitrate': bitrate}
            
            # Metadata options
            metadata = {}
            if title:
                metadata['title'] = title
            if artist:
                metadata['artist'] = artist
            
            # Using metadata requires output options
            # map_metadata=-1 clears old metadata
            stream = ffmpeg.output(stream, output_path, **kwargs, **{'metadata': [f"{k}={v}" for k, v in metadata.items()]})
            
            # Overwrite output
            ffmpeg.run(stream, overwrite_output=True, capture_stdout=True, capture_stderr=True)
            
            return output_path
        except ffmpeg.Error as e:
            # Raise or return error info
            raise RuntimeError(f"FFmpeg error: {e.stderr.decode('utf-8')}") from e
