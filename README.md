# Cashia Credit Engine (CCE)

**cashia-credit-engine ** is the module responsible for the
**credit decision and parameter correction engine** within the Cashia
ecosystem.

It executes the business logic used to:

-   process model applications
-   update internal statistics
-   maintain the credit engine database
-   compute parameter corrections
-   orchestrate credit model updates

cashia-credit-engine is designed to run as an **internal engine** that can be triggered
manually, scheduled, or executed by other Cashia services.

cashia-credit-engine depends on:

-   **cashia-core** -- shared utilities, configuration, storage
    abstraction
-   **cashia-model** -- machine learning models
-   **pandas / numpy** -- data processing
-   **sqlite** -- local engine database

------------------------------------------------------------------------

# 1. Requirements

Before installing cashia-credit-engine, ensure the following are available:

-   Python **3.11**
-   pip
-   Access to the following repositories:

```{=html}
<!-- -->
```
    cashia-core
    cashia-model
    cashia-credit-engine

Recommended tools:

-   **Anaconda / Miniconda**
-   **Visual Studio Code**

------------------------------------------------------------------------

# 2. Environment Setup

## Option A --- Using Conda (recommended)

Create the environment:

``` bash
conda create -n cashia_env python=3.11
```

Activate it:

``` bash
conda activate cashia_env
```

------------------------------------------------------------------------

## Option B --- Using venv

Create a virtual environment:

``` bash
python -m venv cashia_env
```

Activate it:

### Windows

``` bash
cashia_env\Scripts\activate
```

### Linux / macOS

``` bash
source cashia_env/bin/activate
```

------------------------------------------------------------------------

# 3. Installation

Navigate to the root directory containing the Cashia repositories.

Example structure:

    cashia
    │
    ├── cashia-core
    ├── cashia-model
    ├── cashia-credit-engine
    ├── cashia-api
    └── mlp

Install dependencies in editable mode:

``` bash
pip install -e cashia-core
pip install -e cashia-model
pip install -e cashia-credit-engine
```

Editable mode is recommended during development.

------------------------------------------------------------------------

# 4. Project Structure

A typical structure of the cashia-credit-engine project:

    cashia-credit-engine
    │   pyproject.toml
    │   README.md
    │
    └───src
        └───cashia-credit-engine
            │   engine_controller.py
            │   db_manager.py
            │   models_manager.py
            │   statistics_manager.py
            │
            ├── data
            ├── logs
            └── utils

### Key modules

  Module                    Description
  ------------------------- -----------------------------
  `engine_controller.py`    Main engine orchestration
  `db_manager.py`           SQLite database management
  `models_manager.py`       Model loading and execution
  `statistics_manager.py`   Statistics computation
  `utils/`                  Helper utilities

------------------------------------------------------------------------

# 5. Engine Database

cashia-credit-engine maintains an internal **SQLite database** used to track engine
statistics and parameter updates.

Typical tables may include:

-   `stats_ponderation_mdc`
-   `models_statistics`
-   `engine_logs`

The database is created automatically if it does not exist.

Example location:

    Temp/mdc/mdc_db.db

The database location may be dynamically resolved depending on the
execution environment.

------------------------------------------------------------------------

# 6. Command Line Execution

cashia-credit-engine defines entry points in `pyproject.toml` such as:

``` toml
[project.scripts]
cc-engine = "cashia_credit_engine.engine_controller:main"
cce-db = "cashia_credit_engine.db_manager:main"
```

This allows execution from the command line.

Example:

Run the credit engine:

``` bash
cc-engine
```

Initialize or inspect the database:

``` bash
cce-db
```

------------------------------------------------------------------------

# 7. Typical Workflow

The cashia-credit-engine engine usually follows this process:

1.  Load new credit applications
2.  Identify model categories
3.  Compute statistics
4.  Update model parameters
5.  Store results in the engine database

Simplified workflow:

    applications → models → statistics → parameter correction → database update

------------------------------------------------------------------------

# 8. Example Execution

Example manual execution from a terminal:

``` bash
cc-engine
```

Or directly through Python:

``` python
from cashia_credit_engine.engine_controller import main

main()
```

------------------------------------------------------------------------

# 9. Interaction with Other Cashia Modules

cashia-credit-engine interacts with other components as follows:

  Component      Role
  -------------- ----------------------------------
  cashia-core    shared configuration and storage
  cashia-model   machine learning models
  cashia-api     external service layer

cashia-credit-engine acts as the **internal computation engine**, while the API exposes
results externally.

------------------------------------------------------------------------

# 10. Configuration

cashia-credit-engine uses configuration files managed through **cashia-core**.

Typical resources include:

-   model configuration files
-   calibration parameters
-   historical statistics

These resources are accessed through:

``` python
from cashia_core.common_tools.storage import get_storage
from cashia_core.common_tools.configuration.resource_keys import get_resource_path
```

Example:

``` python
storage = get_storage()

config_df = storage.read_excel(
    get_resource_path("configuration")
)
```

------------------------------------------------------------------------

# 11. Development Notes

## Editable install

During development install using:

``` bash
pip install -e cashia-credit-engine
```

## Reinstall after changes

If dependencies change:

``` bash
pip install -e cashia-credit-engine --upgrade
```

------------------------------------------------------------------------

# 12. Troubleshooting

### Database errors

If the database schema changes, the local database may need to be
deleted and recreated.

Example:

    delete mdc_db.db
    ``

    The engine will recreate it on the next run.

    ---

    ### Dependency conflicts

    Ensure that the following packages are installed:

cashia-core cashia-model


    Reinstall if needed:

    ```bash
    pip install -e cashia-core --upgrade
    pip install -e cashia-model --upgrade

------------------------------------------------------------------------

# 13. Future Improvements

Possible future improvements include:

-   migration from SQLite to a centralized database
-   integration with AWS services
-   monitoring and logging improvements

------------------------------------------------------------------------

# Author

Juan Manuel Ahuactzin\
Cashia Project
