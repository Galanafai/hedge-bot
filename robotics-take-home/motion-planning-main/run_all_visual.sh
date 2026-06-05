#!/bin/bash

echo "Starting visual demonstrations for all 5 seeds..."
for seed in {0..4}; do
    echo "=================================================="
    echo "              RUNNING SEED $seed"
    echo "=================================================="
    
    # Run the visual demo directly in this terminal
    PYTHONPATH=. .venv/bin/python3.11 run_sim.py red green blue --seed $seed
    
    echo ""
    echo "Seed $seed finished! Waiting 3 seconds before starting the next one..."
    sleep 3
done

echo "All 5 scenarios have finished!"
