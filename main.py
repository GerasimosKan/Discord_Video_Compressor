import os
import re
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, ttk

from tkinterdnd2 import DND_FILES, TkinterDnD

# Video compression parameters with H.265
preset_params = {
    "AudioList": [
        {"AudioBitrate": 160, "AudioEncoder": "aac", "AudioMixdown": "stereo"}
    ],
    "FileFormat": "mp4",
    "PictureWidth": 1920,
    "PictureHeight": 1080,
    "VideoEncoder": "libx265",
    "VideoFramerate": 60,
    "VideoPreset": "medium",
}

MAX_SIZE_MB = 9.5
BYTES_PER_MB = 1024 * 1024
APP_VERSION = "1.0.0"  # Set your application version here

compression_process = None  # Global variable to manage FFmpeg process


def get_ffmpeg_path():
    """Determine the path to ffmpeg.exe."""
    if getattr(sys, "frozen", False):  # Check if running as a compiled executable
        return os.path.join(sys._MEIPASS, "ffmpeg", "ffmpeg.exe")
    return os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "ffmpeg", "ffmpeg.exe"
    )


ffmpeg_path = get_ffmpeg_path()


def convert_duration_to_seconds(duration):
    """Converts a duration string formatted as HH:MM:SS.ss to total seconds."""
    hours, minutes, seconds = map(float, duration.split(":"))
    return int(hours * 3600 + minutes * 60 + seconds)


def calculate_target_bitrate(duration_seconds):
    """Calculate target video bitrate based on duration and max size."""
    max_bytes = MAX_SIZE_MB * BYTES_PER_MB
    audio_bitrate = preset_params["AudioList"][0]["AudioBitrate"] * 1000
    video_bitrate = (
        max_bytes * 8 - audio_bitrate * duration_seconds
    ) / duration_seconds
    return int(video_bitrate / 1000)


def get_video_duration(input_file):
    try:
        command = [
            ffmpeg_path,
            "-i",
            input_file,
            "-f",
            "null",
            "NUL",
        ]  # Use the determined ffmpeg path
        result = subprocess.run(
            command, stderr=subprocess.PIPE, universal_newlines=True
        )
        if result.returncode != 0:
            raise Exception(result.stderr)
        duration_line = next(
            line for line in result.stderr.splitlines() if "Duration" in line
        )
        duration = duration_line.split("Duration: ")[1].split(",")[0]
        return duration.strip()
    except Exception as e:
        print(f"Error while getting video duration: {e}")
        return None


def check_gpu_support():
    """Check if the system has a compatible NVIDIA GPU."""
    try:
        # Run the command to check for NVIDIA hardware
        result = subprocess.run(
            ["ffmpeg", "-h", "encoder=hevc_nvenc"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        return "hevc_nvenc" in result.stdout
    except Exception as e:
        print(f"Error checking GPU support: {e}")
        return False


def compress_video(
    video_path, save_path, result_label, progress_bar, estimated_time_label
):
    """Compress the video using ffmpeg and update the UI."""
    global compression_process
    duration = get_video_duration(video_path)
    if duration is None:
        result_label.config(text="Failed to get video duration.")
        return

    duration_seconds = convert_duration_to_seconds(duration)  # Convert to seconds
    target_bitrate = calculate_target_bitrate(duration_seconds)

    # Check for GPU support
    use_gpu = check_gpu_support()

    # Set the video encoder based on GPU availability
    video_encoder = "libx265"  # Default to CPU encoding
    if use_gpu:
        video_encoder = "hevc_nvenc"  # Use GPU encoding if available

    command = [
        ffmpeg_path,
        "-i",
        video_path,
        "-c:v",
        video_encoder,
        "-b:v",
        f"{target_bitrate}k",
        "-vf",
        f'scale={preset_params["PictureWidth"]}:{preset_params["PictureHeight"]}',
        "-c:a",
        preset_params["AudioList"][0]["AudioEncoder"],
        "-b:a",
        f'{preset_params["AudioList"][0]["AudioBitrate"]}k',
        save_path,
        "-y",
    ]

    print("FFmpeg command:", " ".join(command))  # Log the command for debugging

    # Use subprocess to run FFmpeg without opening a window
    compression_process = subprocess.Popen(
        command,
        stderr=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
        creationflags=subprocess.CREATE_NO_WINDOW,  # Hide the window on Windows
    )

    # Update the progress bar and estimated time based on ffmpeg output
    for line in compression_process.stderr:
        print(line)  # Log the FFmpeg output line
        if "time=" in line:
            time_match = re.search(r"time=(\d+):(\d+):(\d+.\d+)", line)
            if time_match:
                hours, minutes, seconds = map(float, time_match.groups())
                elapsed_seconds = hours * 3600 + minutes * 60 + seconds
                progress = (elapsed_seconds / duration_seconds) * 100
                progress_bar["value"] = progress
                progress_bar.update()

                # Update the estimated render time
                remaining_seconds = duration_seconds - elapsed_seconds
                estimated_time_label.config(
                    text=f"Estimated time remaining: {remaining_seconds:.2f} seconds"
                )

    compression_process.wait()
    if compression_process.returncode == 0:
        result_label.config(
            text=f"Video successfully compressed and saved to: {save_path}"
        )
    else:
        result_label.config(
            text="Error during compression. Please check the console for details."
        )
        print(
            "Error during compression:", compression_process.stderr.read()
        )  # Log the error output


def handle_video_compression(
    video_path, result_label, progress_bar, estimated_time_label
):
    """Handle the compression workflow."""
    if not os.path.isfile(video_path):
        result_label.config(text="Invalid file. Please provide a valid video file.")
        return

    # Save the compressed video in the same folder as the input video
    base = os.path.basename(video_path)
    name, _ = os.path.splitext(base)
    save_path = os.path.join(os.path.dirname(video_path), f"{name}_Comp.mp4")

    result_label.config(text=f"Processing: {video_path}")
    progress_bar["value"] = 0
    estimated_time_label.config(text="Estimated time remaining: Calculating...")
    threading.Thread(
        target=compress_video,
        args=(video_path, save_path, result_label, progress_bar, estimated_time_label),
    ).start()


def cancel_render():
    """Cancel the ongoing compression process."""
    global compression_process
    if compression_process:
        compression_process.terminate()
        compression_process = None


def on_drop(event, result_label, progress_bar, estimated_time_label):
    handle_video_compression(
        event.data, result_label, progress_bar, estimated_time_label
    )


def browse_file(result_label, progress_bar, estimated_time_label):
    video_path = filedialog.askopenfilename(
        filetypes=[("Video files", "*.mp4 *.mov *.avi *.mkv")],
        title="Select a Video File",
    )
    if video_path:
        handle_video_compression(
            video_path, result_label, progress_bar, estimated_time_label
        )


def open_browse(event, result_label, progress_bar, estimated_time_label):
    browse_file(result_label, progress_bar, estimated_time_label)


def setup_ui():
    """Setup the main UI for the application."""
    root = TkinterDnD.Tk()
    root.title("Discord Video Compressor")
    root.geometry("500x350")  # Fixed window size
    root.configure(bg="#f0f0f0")

    tk.Label(
        root, text="Discord Video Compressor", font=("Arial", 16), bg="#f0f0f0"
    ).pack(pady=(10, 5))

    version_label = tk.Label(
        root, text=f"Version: {APP_VERSION}", bg="#f0f0f0", font=("Arial", 10)
    )
    version_label.pack(pady=(0, 5))

    instruction_label = tk.Label(
        root,
        text="Drag & Drop Video Files Here or Click to Browse",
        width=50,
        height=5,
        bg="#e0e0e0",
        relief="groove",
        anchor="center",
        font=("Arial", 12),
    )
    instruction_label.pack(padx=10, pady=(0, 10))

    instruction_label.bind(
        "<Button-1>",
        lambda event: open_browse(
            event, result_label, progress_bar, estimated_time_label
        ),
    )

    progress_bar = ttk.Progressbar(
        root, orient="horizontal", mode="determinate", length=400
    )
    progress_bar.pack(pady=(0, 10))

    estimated_time_label = tk.Label(
        root, text="Estimated time remaining: ", bg="#f0f0f0", font=("Arial", 10)
    )
    estimated_time_label.pack(pady=(0, 5))

    result_label = tk.Label(root, text="", bg="#f0f0f0", font=("Arial", 10))
    result_label.pack(pady=(10, 0))

    cancel_button = tk.Button(root, text="Cancel Render", command=cancel_render)
    cancel_button.pack(pady=(10, 0))

    instruction_label.drop_target_register(DND_FILES)
    instruction_label.dnd_bind(
        "<<Drop>>",
        lambda event: on_drop(event, result_label, progress_bar, estimated_time_label),
    )

    root.mainloop()


if __name__ == "__main__":
    setup_ui()
