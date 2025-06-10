import os
import yt_dlp
import re
import logging
import time
from urllib.parse import urlparse, parse_qs

class VideoDownloader:
    def __init__(self):
        self.downloads_dir = 'downloads'
        os.makedirs(self.downloads_dir, exist_ok=True)
    
    def is_valid_youtube_url(self, url):
        """Validate if the URL is a valid YouTube URL"""
        youtube_patterns = [
            r'(?:https?://)?(?:www\.)?youtube\.com/watch\?v=[\w-]+',
            r'(?:https?://)?(?:www\.)?youtube\.com/shorts/[\w-]+',
            r'(?:https?://)?youtu\.be/[\w-]+',
            r'(?:https?://)?(?:www\.)?youtube\.com/embed/[\w-]+',
        ]
        
        return any(re.match(pattern, url, re.IGNORECASE) for pattern in youtube_patterns)
    
    def format_duration(self, duration_seconds):
        """Format duration from seconds to readable format"""
        if not duration_seconds or duration_seconds <= 0:
            return "Unknown"
        
        hours = duration_seconds // 3600
        minutes = (duration_seconds % 3600) // 60
        seconds = duration_seconds % 60
        
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        else:
            return f"{minutes:02d}:{seconds:02d}"
    
    def format_view_count(self, view_count):
        """Format view count to readable format"""
        if not view_count or view_count <= 0:
            return "Unknown views"
        
        if view_count >= 1000000:
            return f"{view_count / 1000000:.1f}M views"
        elif view_count >= 1000:
            return f"{view_count / 1000:.1f}K views"
        else:
            return f"{view_count:,} views"
    
    def get_video_info(self, url):
        """Get video information and available formats"""
        try:
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': False,
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                
                if not info:
                    return None
                
                # Extract video information
                video_info = {
                    'title': info.get('title', 'Unknown Title'),
                    'duration': info.get('duration', 0),
                    'uploader': info.get('uploader', 'Unknown'),
                    'view_count': info.get('view_count', 0),
                    'thumbnail': info.get('thumbnail', ''),
                    'description': info.get('description', '')[:200] + '...' if info.get('description') else '',
                    'formats': []
                }
                
                # Process available formats
                formats = info.get('formats', [])
                processed_formats = {}
                
                # Group formats by quality and type
                for fmt in formats:
                    format_id = fmt.get('format_id', '')
                    height = fmt.get('height', 0)
                    width = fmt.get('width', 0)
                    ext = fmt.get('ext', 'mp4')
                    vcodec = fmt.get('vcodec', 'none')
                    acodec = fmt.get('acodec', 'none')
                    filesize = fmt.get('filesize', 0) or fmt.get('filesize_approx', 0)
                    tbr = fmt.get('tbr', 0)
                    
                    # Skip unusable formats
                    if not format_id or format_id.startswith('sb'):  # Skip storyboard formats
                        continue
                    
                    # Determine format type - prioritize combined video+audio formats
                    if vcodec != 'none' and acodec != 'none' and height and height >= 144:
                        # Combined video+audio format (preferred)
                        format_type = 'video'
                        quality = f"{height}p (with audio)"
                    elif vcodec != 'none' and height and height >= 144:
                        # Video-only format (will need audio merging)
                        format_type = 'video'
                        quality = f"{height}p"
                    elif acodec != 'none' and vcodec == 'none':
                        format_type = 'audio'
                        abr = fmt.get('abr', 0)
                        quality = f"Audio {int(abr)}kbps" if abr else f"Audio ({ext.upper()})"
                    else:
                        continue
                    
                    # Create unique key for deduplication
                    key = f"{format_type}_{quality}_{ext}"
                    
                    # Prefer higher quality/filesize formats
                    current_score = filesize or (tbr * 1000 if tbr else 0)
                    existing_score = 0
                    if key in processed_formats:
                        existing_score = processed_formats[key].get('filesize', 0) or (processed_formats[key].get('tbr', 0) * 1000)
                    
                    if key not in processed_formats or current_score > existing_score:
                        processed_formats[key] = {
                            'format_id': format_id,
                            'quality': quality,
                            'ext': ext,
                            'type': format_type,
                            'filesize': filesize,
                            'filesize_mb': round(filesize / 1024 / 1024, 1) if filesize else 0,
                            'tbr': tbr,
                            'height': height,
                            'width': width
                        }
                
                # Sort formats
                video_formats = []
                audio_formats = []
                
                for fmt in processed_formats.values():
                    if fmt['type'] == 'video':
                        video_formats.append(fmt)
                    else:
                        audio_formats.append(fmt)
                
                # Sort video formats by quality (highest first) and prioritize combined formats
                def format_priority(fmt):
                    # Extract quality number for sorting
                    quality_num = int(fmt['quality'].split('p')[0]) if 'p' in fmt['quality'] else 0
                    # Prioritize formats with audio (combined formats)
                    has_audio = '(with audio)' in fmt['quality']
                    return (has_audio, quality_num)
                
                video_formats.sort(key=format_priority, reverse=True)
                
                video_info['formats'] = video_formats + audio_formats
                
                return video_info
                
        except Exception as e:
            logging.error(f"Error getting video info: {str(e)}")
            return None
    
    def download_video(self, url, format_id, download_type='video', progress_callback=None):
        """Download video with specified format"""
        try:
            # Create progress hook
            def progress_hook(d):
                if progress_callback and d['status'] == 'downloading':
                    total = d.get('total_bytes', 0) or d.get('total_bytes_estimate', 0)
                    downloaded = d.get('downloaded_bytes', 0)
                    
                    if total > 0:
                        percentage = (downloaded / total) * 100
                        progress_callback({'percentage': min(percentage, 99)})
            
            # Generate safe filename
            with yt_dlp.YoutubeDL({'quiet': True}) as temp_ydl:
                info = temp_ydl.extract_info(url, download=False)
                if info:
                    title = info.get('title', 'video')
                    safe_title = re.sub(r'[^\w\s-]', '', title).strip()
                    safe_title = re.sub(r'[-\s]+', '_', safe_title)[:50]  # Limit length
                else:
                    safe_title = 'video'
            
            # Configure yt-dlp options
            if download_type == 'audio':
                # Audio download with conversion to MP3
                ydl_opts = {
                    'format': 'bestaudio/best',
                    'outtmpl': os.path.join(self.downloads_dir, f'{safe_title}.%(ext)s'),
                    'progress_hooks': [progress_hook],
                    'quiet': True,
                    'no_warnings': True,
                    'postprocessors': [{
                        'key': 'FFmpegExtractAudio',
                        'preferredcodec': 'mp3',
                        'preferredquality': '192',
                    }]
                }
            else:
                # Video download - always ensure audio is included
                # Use comprehensive format selection to guarantee audio
                if format_id:
                    # First try: specific format + best audio
                    # Second try: best video with audio that matches quality
                    # Third try: best overall format
                    format_selector = f'{format_id}+bestaudio/best[vcodec!="none"][acodec!="none"]/best[height<=?1080][vcodec!="none"][acodec!="none"]/best'
                else:
                    # Always prioritize formats that have both video and audio
                    format_selector = 'best[vcodec!="none"][acodec!="none"]/best[height<=?1080]'
                
                ydl_opts = {
                    'format': format_selector,
                    'outtmpl': os.path.join(self.downloads_dir, f'{safe_title}.%(ext)s'),
                    'progress_hooks': [progress_hook],
                    'quiet': True,
                    'no_warnings': True,
                    'merge_output_format': 'mp4',  # Ensure consistent output format
                    'writesubtitles': False,  # Don't download subtitles
                    'writeautomaticsub': False,  # Don't download auto-generated subtitles
                }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Download the video
                ydl.download([url])
                
                if progress_callback:
                    progress_callback({'percentage': 100})
                
                # Find the downloaded file - look for recent files matching our pattern
                downloaded_files = []
                current_time = time.time()
                
                for file in os.listdir(self.downloads_dir):
                    if file == '.gitkeep':
                        continue
                    
                    file_path = os.path.join(self.downloads_dir, file)
                    if os.path.isfile(file_path):
                        # Check if file was created recently (within last 2 minutes)
                        file_age = current_time - os.path.getctime(file_path)
                        if file_age < 120:  # 2 minutes
                            downloaded_files.append(file)
                
                if downloaded_files:
                    # Get the most recent file
                    downloaded_files.sort(key=lambda x: os.path.getctime(os.path.join(self.downloads_dir, x)), reverse=True)
                    filename = downloaded_files[0]
                    
                    logging.info(f"Successfully downloaded: {filename}")
                    return {
                        'success': True,
                        'filename': filename,
                        'path': os.path.join(self.downloads_dir, filename)
                    }
                else:
                    # Check all files if no recent files found
                    all_files = [f for f in os.listdir(self.downloads_dir) if f != '.gitkeep']
                    if all_files:
                        latest_file = max(all_files, key=lambda x: os.path.getctime(os.path.join(self.downloads_dir, x)))
                        logging.info(f"Found latest file: {latest_file}")
                        return {
                            'success': True,
                            'filename': latest_file,
                            'path': os.path.join(self.downloads_dir, latest_file)
                        }
                    else:
                        return {
                            'success': False,
                            'error': 'No downloaded file found in directory'
                        }
                    
        except Exception as e:
            logging.error(f"Download error: {str(e)}")
            return {
                'success': False,
                'error': f'Download failed: {str(e)}'
            }
    
    def get_direct_download_url(self, url, format_id, download_type='video'):
        """Get direct download URL without storing files locally"""
        # Direct downloads don't support audio merging reliably
        # Return error to force server-side download for videos
        if download_type == 'video':
            return {
                'success': False,
                'error': 'Direct download not supported for videos with audio. Using server download.'
            }
        
        try:
            # Only handle audio downloads directly
            format_selector = 'bestaudio/best'
            
            ydl_opts = {
                'format': format_selector,
                'quiet': True,
                'no_warnings': True,
                'extract_flat': False,
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Extract info to get direct URLs
                info = ydl.extract_info(url, download=False)
                
                if not info:
                    return {
                        'success': False,
                        'error': 'Unable to extract video information'
                    }
                
                # Get the best format URL
                if 'entries' in info:
                    # Handle playlists - get first video
                    video_info = info['entries'][0] if info['entries'] else None
                else:
                    video_info = info
                
                if not video_info:
                    return {
                        'success': False,
                        'error': 'No video information found'
                    }
                
                # Get direct URL from the best audio format
                requested_format = None
                formats = video_info.get('formats', [])
                
                # Find best audio format
                for fmt in formats:
                    if fmt.get('acodec', 'none') != 'none' and fmt.get('vcodec', 'none') == 'none':
                        if not requested_format or (fmt.get('abr', 0) > requested_format.get('abr', 0)):
                            requested_format = fmt
                
                if not requested_format:
                    return {
                        'success': False,
                        'error': 'No suitable audio format found for download'
                    }
                
                # Get the direct URL
                download_url = requested_format.get('url')
                if not download_url:
                    return {
                        'success': False,
                        'error': 'Unable to get direct download URL'
                    }
                
                # Generate filename
                title = video_info.get('title', 'audio')
                safe_title = re.sub(r'[^\w\s-]', '', title).strip()
                safe_title = re.sub(r'[-\s]+', '_', safe_title)[:50]
                filename = f"{safe_title}.mp3"
                
                return {
                    'success': True,
                    'url': download_url,
                    'filename': filename,
                    'filesize': requested_format.get('filesize', 0),
                    'quality': requested_format.get('format_note', 'Unknown')
                }
                
        except Exception as e:
            logging.error(f"Error getting direct download URL: {str(e)}")
            return {
                'success': False,
                'error': f'Failed to get download URL: {str(e)}'
            }
