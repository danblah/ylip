# Import required libraries
import os
import uuid
import inspect
import requests
import base64
import time
from itertools import cycle
import threading
import sys
import glob
import json
import shutil
from io import BytesIO
from threading import Thread

from dotenv import load_dotenv
import openai
from elevenlabs import generate, save

from tinydb import TinyDB, Query
from flask import Flask, render_template_string, request, jsonify
from flask_socketio import SocketIO, emit
import simple_websocket
import gevent

from PIL import Image
from moviepy.editor import ImageClip, AudioFileClip, concatenate_videoclips
import moviepy.video.fx.all as vfx

############################
# Import .env variables
load_dotenv()

# Define API keys
openai.api_key = os.getenv('OPENAI_KEY')
elevenlabs_api_key = os.getenv('ELEVENLABS_KEY')
elai_api_key = os.getenv('ELAI_KEY')

# Define OpenAI settings
openai_gpt_model = os.getenv('OPENAI_MODEL')
openai_gpt_max_tokens = os.getenv('OPENAI_MAX_TOKENS')
openai_gpt_temp = os.getenv('OPENAI_TEMP')
openai_gpt_top_p = os.getenv('OPENAI_TOP_P')

openai_dalle_size = os.getenv('OPENAI_DALLE_SIZE')

# Define Eleven Labs settings
elevenlabs_model = os.getenv('ELEVENLABS_MODEL')
elevenlabs_voice = os.getenv('ELEVENLABS_VOICE')

# Define default prompts
gpt_child_prompt = os.getenv('PROMPT_THEME')
gpt_pre_prompt = os.getenv('PROMPT_PRE')
gpt_image_prompt = os.getenv('PROMPT_IMAGE')
with open(os.getenv('PROMPT_OUTPUT_FORMAT'), 'r') as file:
    gpt_format_prompt = file.read()


############################

# Define database
db = TinyDB('data/'+ os.getenv('DB_NAME'))

# Generate a unique 7 character id
unique_id = str(uuid.uuid4())[:7]

start_time = time.time()

story_data = ""

############################


app = Flask(__name__, static_folder='static')
socketio = SocketIO(app, async_mode='threading')
app.secret_key = os.getenv('SECRET_KEY')

@app.route("/", methods=['GET', 'POST'])
def home():
    global db, gpt_child_prompt, gpt_pre_prompt, gpt_image_prompt
    # Get the most recent story from the database
    stories = db.all()
    story = None
    story_id = None
    initial_movie_status = "Try generating a new movie."

    if stories:
        stories.sort(key=lambda x: x['timestamp'], reverse=True)
        story = stories[0]['story_data']
        story_id = stories[0]['unique_id']
        # Check if 'prompt' exists in story_data and set it as gpt_child_prompt
        if 'prompt_child' in story:
            gpt_child_prompt = story['prompt_child']
            gpt_pre_prompt = story['prompt_pre']
            gpt_image_prompt = story['prompt_image']
    # Define HTML inline
    if story:
        story_paragraphs = story['story']
        story_text = "".join(f"<p>{para}</p>" for para in story_paragraphs.values())
    else:
        story_text = "<p>No story available.</p>"

    movie_file = f"static/stories/{story_id}/{story_id}_movie.mp4" if story_id else None
    if movie_file and os.path.isfile(movie_file):
        movie_element = f"<video width='320' height='240' controls><source src='/{movie_file}' type='video/mp4'></video>"
        direct_link = f"<a href='/{movie_file}'>Video link</a>"
        initial_movie_status = "To generate a new movie, first generate a new story."
    else:
        movie_element = ""
        direct_link = ""
        initial_movie_status = ""
    html = f"""
    <html>
        <head>
            <title>A Young Lady's Illustrated Primer</title>
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <style>
                /* Responsive layout - makes the menu and the content stack on top of each other */
                @media (max-width: 800px) {{
                  .column {{
                    width: 100%;
                    display: block;
                    margin-bottom: 20px;
                  }}
                  body {{
                    font-size: 1.5em; /* Adjust this value to your liking */
                  }}
                }}
                /* Make the paragraph text slightly larger, a more standard easy to read size, responsive */
                p {{
                    font-size: 1.2em;
                }}
                /* Make the video responsive and take up the whole width of the body available */
                video {{
                    width: 80%;
                    height: auto;
                }}
                /* Center all elements, set the maximum width, and add a margin to the right and left sides */
                body {{
                    display: flex;
                    flex-direction: column;
                    align-items: left;
                    max-width: 1024px;
                    margin: 0 auto;
                    padding: 0 25px;
                    font-family: 'Ubuntu', sans-serif;
                }}

                /* Make the textarea full width and auto resize to the amount of text */
                textarea {{
                    width: 100%;
                    min-height: 50px;
                    resize: vertical;
                    overflow: auto;
                }}

                /* Highlight the id messages with a light grey bar, make the text slightly smaller and italic */
                #message_movie, #message_story, #prompt_status {{
                    color: darkgreen;
                    font-size: 0.9em;
                    font-style: italic;
                }}

                .fade-out {{
                    transition: opacity 5s ease-in-out;
                    opacity: 20%;
                }}
            </style>

            <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.0.1/socket.io.js" integrity="sha512-q/dWJ3kcmjBLU4Qc47E4A9kTB4m3wuTY7vkFJDTZKjTs8jhyGQnaUrxa0Ytd0ssMZhbNua9hE+E7Qv1j+DyZwA==" crossorigin="anonymous"></script>
            <script>
                var socket = io();

                socket.on('prompt_status', function(msg) {{
                    var element = document.getElementById('prompt_status');
                    element.classList.remove('fade-out'); // Remove the fade-out class
                    element.innerHTML = msg.status;
                    setTimeout(function() {{ fadeOut('prompt_status'); }}, 3000);

                }});

                function savePromptTheme() {{
                    var prompt_theme = document.getElementById('prompt_theme').value;
                    socket.emit('save_prompt_theme', prompt_theme);
                    console.log('Save theme prompt button pressed');
                }};
                function savePromptPre() {{
                    var prompt_pre = document.getElementById('prompt_pre').value;
                    socket.emit('save_prompt_pre', prompt_pre);
                    console.log('Save pre-prompt button pressed');
                }};
                function savePromptImage() {{
                    var prompt_image = document.getElementById('prompt_image').value;
                    socket.emit('save_prompt_image', prompt_image);
                    console.log('Save image prompt button pressed');
                }};
                function generateStory() {{
                    document.getElementById('generate_story').style.display = 'none';
                    document.getElementById('story').style.display = 'none';
                    document.getElementById('movie').style.display = 'none'; // Hide the current movie when "Generate a new story" has been pressed
                    document.getElementById('direct_link').style.display = 'none'; // Hide the "Video link" url when "Generate a new story" has been pressed
                    socket.emit('generate_story');
                    console.log('Generate new story button pressed');
                }};
                socket.on('new_story', function(msg) {{
                    var story_paragraphs = msg.story;
                    var story_text = "";
                    for (var key in story_paragraphs) {{
                        story_text += "<p>" + story_paragraphs[key] + "</p>";
                    }}
                    document.getElementById('story').innerHTML = story_text;
                    document.getElementById('story').style.display = 'block';
                    document.getElementById('generate_story').style.display = 'block';
                    location.reload(); // Reload the page after the new story has finished generating
                }});
                socket.on('story_status', function(msg) {{
                    document.getElementById('message_story').innerHTML = msg.status;
                }});
                socket.on('movie_status', function(msg) {{
                    document.getElementById('message_movie').innerHTML = msg.status;
                    var movie_file = '/static/stories/' + story_id + '/' + story_id + '_movie.mp4';
                }});
                socket.on('new_movie', function(msg) {{
                    console.log('Movie ready');
                    document.getElementById('movie').innerHTML = "<video width='100%' height='auto' controls><source src='" + msg.status + "' type='video/mp4'></video>";
                    document.getElementById('movie').style.display = 'block';
                    document.getElementById('generate_movie').style.display = 'block'; // Show the "Generate a new movie" button when movie is ready
                    document.getElementById('direct_link').style.display = 'block'; // Show the "Video link" url when movie is ready
                    location.reload(); // Reload the page after the new movie has finished generating
                }});
                function generateMovie() {{
                    document.getElementById('generate_movie').style.display = 'none';
                    document.getElementById('movie').style.display = 'none'; // Hide the current movie when "Generate a new movie" has been pressed
                    document.getElementById('direct_link').style.display = 'none'; // Hide the "Video link" url when "Generate a new movie" has been pressed
                    socket.emit('create_movie');
                    console.log('Generate new movie button pressed');
                }};
                function fadeOut(id) {{
                    var element = document.getElementById(id);
                    element.classList.add('fade-out');
                }}
            </script>

        </head>
        <body>
            <h1>A Young Lady's Illustrated Primer</h1>
            <div class="column">
                <h2>Story time</h2>
                <h3>Current prompts</h3>
                <p id="prompt_status">Start by saving a prompt</p>
                <h4>Child's main theme prompt</h4>
                <p><textarea id="prompt_theme">{gpt_child_prompt}</textarea></p>
                <p><button onclick="savePromptTheme()" type="button" value="submit">Save theme prompt</button></p>
                <details>
                    <summary>Additional Prompts</summary>
                    <h4>Story pre-prompt</h4>
                    <p><textarea id="prompt_pre">{gpt_pre_prompt}</textarea></p>
                    <p><button onclick="savePromptPre()" type="button">Save pre-prompt</button></p>
                    <h4>Image generation pre-prompt</h4>
                    <p><textarea id="prompt_image">{gpt_image_prompt}</textarea></p>
                    <p><button onclick="savePromptImage()" type="button">Save image prompt</button></p>
                </details>
                <p id="save_status"></p>
            </div>
            <div class="column">
                <h3>Current story</h3>
                <p id="message_story"></p>
                <div id="story" style="display: block;">{story_text}</div>
                <button id="generate_story" onclick="generateStory()" type="button">Generate a new story</button>
            </div>
            <div class="column">
                <h3>Current movie</h3>
                <p id="message_movie">{initial_movie_status}</p>
                <div id="movie" style="display: block;">{movie_element}</div>
                <p id="direct_link" style="display: block;">{direct_link}</p>
                <button id="generate_movie" onclick="generateMovie()" type="button" style="display: block;">Generate a new movie</button>
            </div>
            <div class="column">
              <h2>Question time</h2>
            </div>
        </body>
    </html>

    """
    return render_template_string(html)


@socketio.on('save_prompt_theme')
def handle_save_prompt(prompt_theme):
    global gpt_child_prompt
    gpt_child_prompt = prompt_theme
    emit('prompt_status', {'status': 'Theme prompt saved successfully!'})

    print(f"{time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())} - Saved new prompt_theme: {gpt_child_prompt}")

@socketio.on('save_prompt_pre')
def handle_save_prompt(prompt_pre):
    global gpt_pre_prompt
    gpt_pre_prompt = prompt_pre
    emit('prompt_status', {'status': 'Pre prompt saved successfully!'})

    print(f"{time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())} - Saved new prompt_pre: {gpt_pre_prompt}")

@socketio.on('save_prompt_image')
def handle_save_prompt(prompt_image):
    global gpt_image_prompt
    gpt_image_prompt = prompt_image
    emit('prompt_status', {'status': 'Image prompt saved successfully!'})

    print(f"{time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())} - Saved new prompt_image: {gpt_image_prompt}")

@socketio.on('generate_story')
def generate_story():
    global unique_id, story_data, gpt_child_prompt, gpt_pre_prompt, gpt_format_prompt, db

    print(f"{time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())} - {inspect.stack()[0][3]}: Starting")
    try:
        gpt_full_prompt = gpt_pre_prompt + " The story's main theme is: " + gpt_child_prompt + "\n" + gpt_image_prompt + "\n" + gpt_format_prompt

        # Generate new story text
        print(f"{time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())} - {inspect.stack()[0][3]}: About to request a new story, here's the prompt:" + "\n" + gpt_full_prompt)
        emit('story_status', {'status': 'Generating a new story'})
        
        def generate_completion():
            global completion
            completion = openai.ChatCompletion.create(
                model="gpt-4",
                max_tokens=4096,
                temperature=0.15,
                top_p=1,
                messages=[
                    {"role": "user", "content": gpt_full_prompt}
                ]
            )

        def emit_status():
            messages = cycle([
                'Okay, let me think...',
                'Shhhh... Loud noise distracts me!',
                'Here we go, got an idea...',
                'Now, where did I put my pencil...',
                'Oh no! Do you have any paper???',
                'Getting warmed up now...',
                'Creative juices are really flowing!!!',
                'Just putting on the finishing touches...',
                'Almost done...'
            ])
            while thread.is_alive():
                socketio.emit('story_status', {'status': next(messages)}, namespace='/')
                time.sleep(5)

        thread = threading.Thread(target=generate_completion)
        thread.start()

        emit_thread = threading.Thread(target=emit_status)
        emit_thread.start()

        thread.join()
        emit_thread.join()

       
        # Remove leading and trailing quotes from story_text
        story_text = completion.choices[0].message.content.strip('"')
        print(f"{time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())} - {inspect.stack()[0][3]}: Got a new story: " + "\n" + story_text)
        emit('story_status', {'status': 'Here comes a brand new story!'})
        # Load the JSON data from story_text
        # Added json.loads() inside a try-except block to handle JSONDecodeError
        try:
            # Replace escaped double quotes with actual double quotes
            story_text = story_text.replace('\\"', '"')
            story_data = json.loads(story_text)

            # Insert the prompts as a separate objects in the story_data dictionary
            story_data.update({"prompt_child": gpt_child_prompt})
            story_data.update({"prompt_pre": gpt_pre_prompt})
            story_data.update({"prompt_image": gpt_image_prompt})

        except json.JSONDecodeError as json_err:
            print(f"{time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())} - {inspect.stack()[0][3]}: Error in parsing JSON: {json_err}")
            return

        # Save the contents of story_data to db.json with a timestamp
        db.insert({'timestamp': time.time(), 'unique_id': unique_id, 'story_data': story_data})

        # Emit the new story to the client
        socketio.emit('new_story', {'story': story_data['story']})

    except Exception as e:
        print(f"{time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())} - {inspect.stack()[0][3]}: Error in function: {e}")

@socketio.on('create_movie')
def create_movie():
    global db

    print(f"{time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())} - Running create_movie")

    # Get the most recent story from the database
    stories = db.all()
    stories.sort(key=lambda x: x['timestamp'], reverse=True)
    story_data = stories[0]['story_data']
    story_id = stories[0]['unique_id']
    story_folder = 'static/stories/' + story_id

    # Check if a directory named static/stories/story_id exists. if not create it.
    if not os.path.exists(story_folder):
        os.makedirs(story_folder, exist_ok=True)


    # In the directory named story_id, check if any a video already exist.
    video_clip = glob.glob(f"{story_folder}/*.mp4")

    # In the directory named story_id, check if images already exist.
    image_clips = glob.glob(f"{story_folder}/*.png")

    # In the directory named story_id, check if audio files already exist.
    audio_clips = glob.glob(f"{story_folder}/*.wav")

    try:
        if video_clip:
            print(f"{time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())} - {inspect.stack()[0][3]}: Existing video clip, skipping creation")
            emit('movie_status', {'status': 'Existing movie, skipping creation'})
            emit('new_movie', {'status': f"{story_folder}/{story_id}_movie.mp4"})

    except Exception as e:
        print(f"{time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())} - {inspect.stack()[0][3]}: error checking for existing video clip {e}")

    try:
        if not video_clip:
            #Check if everything exists to make a movie

            # Check if audio_clips exist. if not, generate audio_clips
            print(f"{time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())} - {inspect.stack()[0][3]}: Checking for existing audio clips")
            try:
                emit('movie_status', {'status': 'Checking for existing audio files'})
            except RuntimeError as e:
                print(f"{time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())} - {inspect.stack()[0][3]}: Error emitting status: {e}")
                return

            if not audio_clips:
                print(f"{time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())} - {inspect.stack()[0][3]}: No audio files, generating")
                emit('movie_status', {'status': 'Creating text-to-speech audio files'})
                generate_audio()
                # Wait for the audio files to be generated before proceeding
                # Check for each story_paragraph in story_data
                for i in range(1, len(story_data['story']) + 1):
                    while not os.path.exists(f"{story_folder}/{story_id}_story_paragraph_{i}.wav"):
                        time.sleep(1)
                print(f"{time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())} - {inspect.stack()[0][3]}: Audio file generation complete")

            print(f"{time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())} - {inspect.stack()[0][3]}: Existing audio files, skipping generation")

    except Exception as e:
        print(f"{time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())} - {inspect.stack()[0][3]}: Audio regeneration error: {e}")

    try:
        if not video_clip:
            # Check if images exist. if not, generate them
            print(f"{time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())} - {inspect.stack()[0][3]}: Checking for existing image files")
            emit('movie_status', {'status': 'Checking for existing image files'})

            if not image_clips:
                print(f"{time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())} - {inspect.stack()[0][3]}: No image files")
                # Check if there is an image_urls object within story_data
                if "image_urls" not in story_data:
                    print(f"{time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())} - {inspect.stack()[0][3]}: No image files, generating")
                    emit('movie_status', {'status': 'Generating new images to go with the story'})
                    # If not, run the generate_images() function and wait until the function completes
                    generate_images()
                    while "image_urls" not in story_data:
                        time.sleep(1)

                # Check if the image_urls are responding 403, if so regenerate images
                print(f"{time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())} - {inspect.stack()[0][3]}: Checking if images are expired") 
                emit('movie_status', {'status': 'Checking if image URLs have expired'})       
                image_url = story_data["image_urls"][f"image_url_1"]
                response = requests.get(image_url)
                if response.status_code == 403:
                    print(f"{time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())} - {inspect.stack()[0][3]}: Image urls expired, regenerating images")
                    emit('movie_status', {'status': 'Image urls expired, regenerating images'})
                    generate_images()

                    print(f"{time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())} - {inspect.stack()[0][3]}: Image regeneration success")
                    emit('movie_status', {'status': 'Image regeneration success'})

    except Exception as e:
        print(f"{time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())} - {inspect.stack()[0][3]}: Image regeneration error: {e}")
                        
    finally:
        if not video_clip:

            # Download images
            print(f"{time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())} - {inspect.stack()[0][3]}: downloading images")
            emit('movie_status', {'status': 'Downloading images to use in the video'})
            i = 1
            while True:
                image_filename = f"{story_folder}/{story_id}_image_url_{i}.png"
                
                if not os.path.exists(image_filename):
                    if f"image_url_{i}" in story_data["image_urls"]:
                        image_url = story_data["image_urls"][f"image_url_{i}"]
                        response = requests.get(image_url)
                        if response.status_code == 200:
                            with open(image_filename, 'wb') as f:
                                f.write(response.content)
                                print(f"{time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())} - {inspect.stack()[0][3]}: downloaded new image: {image_filename}")
                        else:
                            break
                    else:
                        break
                i += 1
            print(f"{time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())} - {__name__}: images downloaded")
            emit('movie_status', {'status': 'Images downloaded'})

            # Generate video clips from the audio_clips and image_clips
            print(f"{time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())} - {__name__}: creating movie clips")
            emit('movie_status', {'status': 'Combining the audio and image files into video clips'})
            i = 1
            video_clips = []  # Initialize video_clips as an empty list
            while True:
                audio_filename = f"{story_folder}/{story_id}_story_paragraph_{i}.wav"
                image_filename = f"{story_folder}/{story_id}_image_url_{i}.png"
                if os.path.exists(audio_filename) and os.path.exists(image_filename):
                    audio = AudioFileClip(audio_filename)
                    image = ImageClip(image_filename, duration=audio.duration)
                    video_clip = image.set_audio(audio)
                    video_clips.append(video_clip.fx(vfx.speedx, 0.95))  # Slow down the video by 5%
                else:
                    break
                i += 1

            # Create a single video from all of the video_clips
            if video_clips:
                print(f"{time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())} - {__name__}: creating the movie")
                emit('movie_status', {'status': 'Combining video clips into a single movie'})

                final_video = concatenate_videoclips(video_clips)
                final_video.write_videofile(f"{story_folder}/{story_id}_movie.mp4", fps=24, codec='libx264', audio_codec='aac')
                    
                print(f"{time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())} - {__name__}: movie created success")
                emit('movie_status', {'status': 'Movie creation success'})
                emit('new_movie', {'status': f"{story_folder}/{story_id}_movie.mp4"})

# Generate images for each image_prompt in story_data, save the image URLs, and update the database
def generate_images():
    global unique_id, db
    try:
        print(f"{time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())} - Running generate_images")

        # Get the most recent story from the database
        stories = db.all()
        stories.sort(key=lambda x: x['timestamp'], reverse=True)
        story_data = stories[0]['story_data']
        story_id = stories[0]['unique_id']

        # Initialize an empty dictionary for image_urls
        story_data["image_urls"] = {}

        print(f"{time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())} - print story_data: {story_data}")

        i = 1
        while f"image_prompt_{i}" in story_data["image_prompts"]:
            prompt = story_data["image_prompts"][f"image_prompt_{i}"]
            
            print(f"{time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())} - Generating new image, prompt: {prompt}")

            response = openai.Image.create(
                prompt=prompt,
                n=1,
                size="1024x1024",
            )
            image_url = response["data"][0]["url"]

            # Save the image URL as image_url_{i} in the story_data object
            story_data["image_urls"][f"image_url_{i}"] = image_url

            print(f"{time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())} - Request sent:\n{prompt}\n\nResponse received:\n{image_url}\n\n")
            i += 1
        
        print(f"{time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())} - Image generation complete, new story_data: {story_data}")

        # Update the story_data in the database with the new image_urls
        db.update({'story_data': story_data}, Query().unique_id == story_id)

        create_movie()

    except Exception as e:
        print(f"{time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())} - Error in generate_images function: {e}\n")

def generate_audio():
    global db
    try:
        print(f"{time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())} - {inspect.stack()[0][3]}: Running generate_audio")

        # Get the most recent story from the database
        stories = db.all()
        stories.sort(key=lambda x: x['timestamp'], reverse=True)
        story_data = stories[0]['story_data']
        story_id = stories[0]['unique_id']
        story_folder = 'static/stories/' + story_id

        # Initialize an empty dictionary for audio_urls
        story_data["audio_urls"] = {}

        print(f"{time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())} - {inspect.stack()[0][3]}: print story_data: {story_data}")

        # Check if a directory named story_id exists. if not create it.
        if not os.path.exists(story_folder):
            os.makedirs(story_folder, exist_ok=True)

        i = 1
        while f"story_paragraph_{i}" in story_data["story"]:
            text = story_data["story"][f"story_paragraph_{i}"]
            
            print(f"{time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())} - {inspect.stack()[0][3]}: Generating new audio, text: {text}")

            audio_bytes = generate(
                api_key=elevenlabs_api_key,
                text=text,
                voice="Bella",
                model="eleven_monolingual_v1"
            )

            # Save the audio file as story_paragraph_{i}.wav in the unique_id directory
            filename = f"{story_folder}/{story_id}_story_paragraph_{i}.wav"
            save(
                audio=audio_bytes,               # Audio bytes (returned by generate)
                filename=filename,               # Filename to save audio to
            )
            i += 1

    except Exception as e:
        print(f"{time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())} - {inspect.stack()[0][3]}: Error in generate_audio function: {e}")

if __name__ == '__main__':
    socketio.run(app,port=5000,debug=True)
    serve(app)