var socket = io.connect('http://' + document.domain + ':' + location.port);
var intervalId = null;
var dotCount = 0;
socket.on('new_story', function(msg) {{
    var story_paragraphs = msg.story;
    var story_text = "";
    for (var key in story_paragraphs) {{
        story_text += "<p>" + story_paragraphs[key] + "</p>";
    }}
    document.getElementById('story').innerHTML = story_text;
    document.getElementById('story').style.display = 'block';
    document.getElementById('spinner_story').style.display = 'none';
    document.getElementById('generate_story').style.display = 'block';
    clearInterval(intervalId);
    location.reload(); // Reload the page after the new story has finished generating
}});
socket.on('prompt_saved', function(msg) {{
    document.getElementById('save_status').innerHTML = msg.status;
    document.getElementById('story').style.display = 'none';
    document.getElementById('movie').style.display = 'none';
    document.getElementById('generate_story').style.display = 'block';
    document.getElementById('generate_movie').style.display = 'block';
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
function savePromptImage() {{c
    var prompt_image = document.getElementById('prompt_image').value;
    socket.emit('save_prompt_image', prompt_image);
    console.log('Save image prompt button pressed');
}};
function generateStory() {{
    document.getElementById('spinner_story').style.display = 'block';
    document.getElementById('generate_story').style.display = 'none';
    document.getElementById('story').style.display = 'none';
    document.getElementById('movie').style.display = 'none'; // Hide the current movie when "Generate a new story" has been pressed
    document.getElementById('direct_link').style.display = 'none'; // Hide the "Video link" url when "Generate a new story" has been pressed
    socket.emit('generate_story');
    console.log('Generate new story button pressed');
    intervalId = setInterval(function() {{
        dotCount = (dotCount + 1) % 4;
        var dots = new Array(dotCount + 1).join(".");
        document.getElementById('spinner_story').innerHTML = 'Generating story (~30s)' + dots;
    }}, 1000);
}};

function generateMovie() {{
    var movie_file = '/static/stories/{story_id}/{story_id}_movie.mp4';
    var xhr = new XMLHttpRequest();
    xhr.open('HEAD', movie_file, false);
    xhr.send();
    if (xhr.status == "404") {{
        document.getElementById('spinner_movie').style.display = 'block';
        document.getElementById('generate_movie').style.display = 'block';
        document.getElementById('movie').style.display = 'none';
        socket.emit('create_movie');
        console.log('Generate new movie button pressed');
        intervalId = setInterval(function() {{
            dotCount = (dotCount + 1) % 4;
            var dots = new Array(dotCount + 1).join(".");
            document.getElementById('spinner_movie').innerHTML = 'Generating movie (~60s)' + dots;
        }}, 1000);
    }} else {{
        console.log('Movie already exists');
        document.getElementById('generate_movie').style.display = 'none'; // Show the "Generate a new movie" button if movie already exists
    }}
}};

socket.on('movie_created', function(msg) {{
    var movie_file = '/static/stories/{story_id}/{story_id}_movie.mp4';
    var xhr = new XMLHttpRequest();
    xhr.open('HEAD', movie_file, false);
    xhr.send();
    if (xhr.status == "404") {{
        console.log('Movie not yet ready');
    }} else {{
        console.log('Movie ready');
        document.getElementById('movie').innerHTML = "<video width='100%' height='auto' controls><source src='" + movie_file + "' type='video/mp4'></video>";
        document.getElementById('movie').style.display = 'block';
        document.getElementById('spinner_movie').style.display = 'none';
        document.getElementById('generate_movie').style.display = 'block'; // Show the "Generate a new movie" button when movie is ready
        document.getElementById('direct_link').style.display = 'block'; // Show the "Video link" url when movie is ready
        clearInterval(intervalId);
        location.reload(); // Reload the page after the new movie has finished generating
    }}
}});