import os
import logging
from flask import Flask, render_template, request, jsonify, send_file
from flask_cors import CORS
from video_downloader import VideoDownloader
import mimetypes

# Configure logging
logging.basicConfig(level=logging.DEBUG)

app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "dev-secret-key-change-in-production")
CORS(app)

downloader = VideoDownloader()

@app.route('/')
def index():
    """Main page with YouTube downloader interface"""
    return render_template('index.html')

@app.route('/get_video_info', methods=['POST'])
def get_video_info():
    """Get video information and available formats"""
    try:
        data = request.get_json()
        url = data.get('url', '').strip()
        
        if not url:
            return jsonify({'error': 'Please provide a valid YouTube URL'}), 400
        
        # Validate YouTube URL
        if not downloader.is_valid_youtube_url(url):
            return jsonify({'error': 'Please provide a valid YouTube URL. Supported formats: youtube.com/watch, youtu.be, youtube.com/shorts, youtube.com/embed'}), 400
        
        # Get video information
        video_info = downloader.get_video_info(url)
        
        if not video_info:
            return jsonify({'error': 'Unable to fetch video information. Please check the URL and try again.'}), 400
        
        # Format duration and view count for display
        video_info['formatted_duration'] = downloader.format_duration(video_info.get('duration', 0))
        video_info['formatted_views'] = downloader.format_view_count(video_info.get('view_count', 0))
        
        return jsonify({
            'success': True,
            'video_info': video_info
        })
        
    except Exception as e:
        logging.error(f"Error getting video info: {str(e)}")
        return jsonify({'error': 'An error occurred while fetching video information. Please try again.'}), 500

@app.route('/download', methods=['POST'])
def download_video():
    """Get direct download URL for client-side download"""
    try:
        data = request.get_json()
        url = data.get('url', '').strip()
        format_id = data.get('format_id', '')
        download_type = data.get('download_type', 'video')
        
        if not url or not format_id:
            return jsonify({'error': 'Missing required parameters. Please select a format and try again.'}), 400
        
        # Validate YouTube URL
        if not downloader.is_valid_youtube_url(url):
            return jsonify({'error': 'Please provide a valid YouTube URL'}), 400
        
        # Get direct download URL
        download_result = downloader.get_direct_download_url(url, format_id, download_type)
        
        if download_result['success']:
            return jsonify({
                'success': True,
                'download_url': download_result['url'],
                'filename': download_result['filename'],
                'filesize': download_result.get('filesize', 0),
                'quality': download_result.get('quality', '')
            })
        else:
            return jsonify({'error': download_result['error']}), 400
        
    except Exception as e:
        logging.error(f"Error getting download URL: {str(e)}")
        return jsonify({'error': 'An error occurred while preparing the download. Please try again.'}), 500

@app.route('/server_download', methods=['POST'])
def server_download():
    """Download video to server and return download URL"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data received'}), 400
            
        url = data.get('url', '').strip()
        format_id = data.get('format_id', '')
        download_type = data.get('download_type', 'video')
        
        logging.info(f"Server download request: URL={url}, Format={format_id}, Type={download_type}")
        
        if not url or not format_id:
            return jsonify({'error': 'Missing required parameters'}), 400
        
        # Validate YouTube URL
        if not downloader.is_valid_youtube_url(url):
            return jsonify({'error': 'Please provide a valid YouTube URL'}), 400
        
        # Download video to server
        logging.info("Starting video download...")
        download_result = downloader.download_video(url, format_id, download_type)
        logging.info(f"Download result: {download_result}")
        
        if download_result['success']:
            filename = download_result['filename']
            
            # Return success with download URL instead of serving file directly
            return jsonify({
                'success': True,
                'download_url': f'/download_file/{filename}',
                'filename': filename
            })
        else:
            logging.error(f"Download failed: {download_result.get('error', 'Unknown error')}")
            return jsonify({'error': download_result.get('error', 'Download failed')}), 400
        
    except Exception as e:
        logging.error(f"Error in server download: {str(e)}", exc_info=True)
        return jsonify({'error': f'Server error: {str(e)}'}), 500

@app.route('/download_file/<filename>')
def download_file(filename):
    """Serve downloaded files with optimized streaming"""
    try:
        import os
        file_path = os.path.join(downloader.downloads_dir, filename)
        
        if not os.path.exists(file_path):
            return jsonify({'error': 'File not found'}), 404
        
        # Determine MIME type
        mime_type, _ = mimetypes.guess_type(file_path)
        if not mime_type:
            if filename.endswith('.mp3'):
                mime_type = 'audio/mpeg'
            elif filename.endswith('.mp4'):
                mime_type = 'video/mp4'
            else:
                mime_type = 'application/octet-stream'
        
        logging.info(f"Serving file: {file_path} ({mime_type})")
        
        # Use Flask's optimized send_file for better performance
        return send_file(
            file_path,
            as_attachment=True,
            download_name=filename,
            mimetype=mime_type
        )
        
    except Exception as e:
        logging.error(f"Error serving file: {str(e)}")
        return jsonify({'error': 'File serving error'}), 500

@app.errorhandler(404)
def not_found_error(error):
    return render_template('index.html'), 404

@app.errorhandler(500)
def internal_error(error):
    logging.error(f"Internal server error: {str(error)}")
    return jsonify({'error': 'Internal server error. Please try again later.'}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
