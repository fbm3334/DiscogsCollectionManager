# DiscogsCollectionManager

A Discogs collection manager written in Python and using the NiceGUI UI library.

# Running

The minimum supported Python version is 3.12 - older versions may work but are not supported.

## Recommended - use `uv`

Using `uv` is recommended as it will automatically download the required Python
version, create the virtual environment and download all of the required
packages.

1. Ensure `uv` is installed on your system - [the documentation](https://docs.astral.sh/uv/)
contains install instructions.
2. Clone the repository to your PC.
3. Run by entering the following command in your terminal:

        > uv run src/main.py
        
## Alternative - manually create the virtual environment

1. Clone the repository to your PC.
2. Create a Python virtual environment.
3. Install the required dependencies from requirements.txt:
   
        > pip install -r requirements.txt
   
4. Run the Python script:
   
        > python src/main.py

# License
This software is licensed under the MIT License - see [License](LICENSE) for more details.
