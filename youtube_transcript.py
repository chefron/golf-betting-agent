import os
import googleapiclient.discovery
from googleapiclient.errors import HttpError
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

def get_video_details(api_key, video_id):
    """Get video details using YouTube Data API"""
    youtube = googleapiclient.discovery.build("youtube", "v3", developerKey=api_key)
    
    request = youtube.videos().list(
        part="snippet",
        id=video_id
    )
    
    response = request.execute()
    
    if response["items"]:
        return {
            "title": response["items"][0]["snippet"]["title"],
            "channel": response["items"][0]["snippet"]["channelTitle"],
            "published_at": response["items"][0]["snippet"]["publishedAt"],
            "description": response["items"][0]["snippet"]["description"]
        }
    else:
        return None

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
    with open(filename, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"Transcript saved to {filename}")

def main():
    parser = argparse.ArgumentParser(description="Fetch YouTube video transcripts")
    parser.add_argument("--url", required=True, help="YouTube video URL or ID")
    parser.add_argument("--api_key", help="YouTube Data API key (or set YOUTUBE_API_KEY env variable)")
    parser.add_argument("--output", help="Output filename (default: transcript.txt)")
    
    args = parser.parse_args()
    
    # Get API key from args or environment
    api_key = args.api_key or os.environ.get("YOUTUBE_API_KEY")
    if not api_key:
        print("Warning: No YouTube API key provided. Only transcripts will be fetched, not video details.")
    
    # Get video ID from URL
    video_id = get_video_id_from_url(args.url)
    print(f"Fetching transcript for video ID: {video_id}")
    
    # Get video details if API key is available
    video_details = None
    if api_key:
        video_details = get_video_details(api_key, video_id)
        if video_details:
            print(f"Title: {video_details['title']}")
            print(f"Channel: {video_details['channel']}")
            print(f"Published: {video_details['published_at']}")
    
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
    
    # Save video details if available
    if video_details:
        details_file = output_file.replace(".txt", "_details.json")
        with open(details_file, "w", encoding="utf-8") as f:
            json.dump(video_details, f, indent=2)
        print(f"Video details saved to {details_file}")

if __name__ == "__main__":
    main()