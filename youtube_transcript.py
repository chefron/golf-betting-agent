import os
from youtube_transcript_api import YouTubeTranscriptApi
import argparse
import json

def get_video_id_from_url(url):
    """Extract video ID from a YouTube URL"""
    if "youtube.com/watch?v=" in url:
        return url.split("youtube.com/watch?v=")[1].split("&")[0]
    elif "youtu.be/" in url:
        return url.split("youtu.be/")[1].split("?")[0]
    else:
        return url  # Assume it's already a video ID

def get_transcript(video_id):
    """Get transcript using youtube_transcript_api"""
    try:
        transcript_list = YouTubeTranscriptApi.get_transcript(video_id)
        return transcript_list
    except Exception as e:
        print(f"Error fetching transcript: {e}")
        return None

def format_transcript(transcript_list):
    """Format transcript into readable text"""
    if not transcript_list:
        return ""
    
    full_text = ""
    for item in transcript_list:
        full_text += item["text"] + " "
    
    return full_text

def save_transcript(text, filename):
    """Save transcript to a file"""
    # Create transcripts directory if it doesn't exist
    os.makedirs("transcripts", exist_ok=True)
    
    # If filename doesn't include a path, save it to the transcripts directory
    if not os.path.dirname(filename):
        filename = os.path.join("transcripts", filename)
        
    with open(filename, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"Transcript saved to {filename}")

def main():
    parser = argparse.ArgumentParser(description="Fetch YouTube video transcripts")
    parser.add_argument("--url", required=True, help="YouTube video URL or ID")
    parser.add_argument("--output", help="Output filename (default: transcript.txt)")
    
    args = parser.parse_args()
    
    # Get video ID from URL
    video_id = get_video_id_from_url(args.url)
    print(f"Fetching transcript for video ID: {video_id}")
    
    # Get transcript
    transcript_list = get_transcript(video_id)
    if not transcript_list:
        print("Failed to fetch transcript. Make sure the video has closed captions.")
        return
    
    # Format transcript
    transcript_text = format_transcript(transcript_list)
    
    # Save transcript
    output_file = args.output or "transcript.txt"
    save_transcript(transcript_text, output_file)

if __name__ == "__main__":
    main()