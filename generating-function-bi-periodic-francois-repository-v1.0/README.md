# Generating Function for the Bi-Periodic François Sequence: Algorithm Analysis and Performance Modeling

This repository contains the Python implementation and experimental workflow used to evaluate the computational behavior of a single generating function formulation for the bi-periodic François sequence.

## Repository structure

```generating-function-bi-periodic-francois-repository
.
├── src/
│   └── generating_function_analysis.py
├── docs/
│   ├── code_availability_statement.md
│   └── original_uploaded_code.txt
├── requirements.txt
├── LICENSE
├── CITATION.cff
└── README.md
```

## Experimental design

The script evaluates the workload using 10,000, 100,000, and 1,000,000 iterations. The measured metrics are runtime, time per iteration, throughput, peak memory usage, CPU package power if Intel Power Gadget is available, and computed energy.

## Complexity analysis

- Single generating function calculation: `O(1)`
- Workload of `N` iterations: `O(N)`
- Space complexity: `O(1)`

## Installation

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

For Linux/macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Usage

Run without Intel Power Gadget:

```bash
python src/generating_function_analysis.py --no-ipg
```

Run a smaller test:

```bash
python src/generating_function_analysis.py --iterations 10000 100000 --runs 3 --no-ipg
```

Run with Intel Power Gadget enabled on Windows:

```bash
python src/generating_function_analysis.py
```

## Output

The script creates:

- `raw_results.csv`
- `summary_results.csv`
- `performance_report.txt`
- publication-resolution PNG figures in `figures/`

## Code availability statement

https://github.com/isanlialp/generating-function-bi-periodic-francois

## License

MIT License.
