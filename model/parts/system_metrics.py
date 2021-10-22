"""
# System Metrics

Calculation of metrics such as validator operational costs and yields.
"""

import typing
import numpy as np

import model.constants as constants
from model.types import Percentage, Gwei, ETH

from model.system_parameters import validator_environments  

def policy_validator_costs(
    params, substep, state_history, previous_state
) -> typing.Dict[str, any]:
    """
    ## Validator Costs Policy Function
    Calculate the aggregate validator costs.
    """
    # Parameters
    dt = params["dt"]

    validator_hardware_costs_per_epoch = params["validator_hardware_costs_per_epoch"]
    validator_cloud_costs_per_epoch = params["validator_cloud_costs_per_epoch"]
    validator_third_party_costs_per_epoch = params[
        "validator_third_party_costs_per_epoch"
    ]

    # State Variables
    eth_price = previous_state["eth_price"]
    number_of_validators = previous_state["number_of_active_validators"]
    total_online_validator_rewards = previous_state["total_online_validator_rewards"]
    validator_percentage_distribution = previous_state["validator_percentage_distribution"]
    validator_count_distribution = previous_state["validator_count_distribution"]

    validator_hardware_costs = (
        validator_count_distribution * validator_hardware_costs_per_epoch * dt
    )

    validator_cloud_costs = (
        validator_count_distribution * validator_cloud_costs_per_epoch * dt
    )

    validator_third_party_costs = (
        validator_percentage_distribution
        * validator_third_party_costs_per_epoch  # % of total
        * total_online_validator_rewards
    )
    validator_third_party_costs /= constants.gwei  # Convert from Gwei to ETH
    validator_third_party_costs *= eth_price  # Convert from ETH to Dollars

    # Calculate total validator costs per validator type and total network costs
    validator_costs = (
        validator_hardware_costs + validator_cloud_costs + validator_third_party_costs
    )
    total_network_costs = validator_costs.sum(axis=0)

    return {
        "validator_hardware_costs": validator_hardware_costs,
        "validator_cloud_costs": validator_cloud_costs,
        "validator_third_party_costs": validator_third_party_costs,
        "validator_costs": validator_costs,
        "total_network_costs": total_network_costs,
    }


def policy_validator_yields(
    params, substep, state_history, previous_state
) -> typing.Dict[str, any]:
    """
    ## Validator Yields Policy Function
    Calculate the aggregate validator revenue and profit yields.
    """
    # Parameters
    dt = params["dt"]
    
    # State Variables
    eth_price = previous_state["eth_price"]
    eth_staked = previous_state["eth_staked"]
    validator_costs = previous_state["validator_costs"]
    total_network_costs = previous_state["total_network_costs"]
    total_online_validator_rewards = previous_state["total_online_validator_rewards"]
    average_effective_balance = previous_state["average_effective_balance"]
    validator_count_distribution = previous_state["validator_count_distribution"]
    validator_percentage_distribution = previous_state["validator_percentage_distribution"]


    # Calculate ETH staked per validator type
    validator_eth_staked = validator_count_distribution * average_effective_balance
    validator_eth_staked /= constants.gwei  # Convert from Gwei to ETH

    # Calculate the revenue per validator type
    validator_revenue = (
        validator_percentage_distribution * total_online_validator_rewards
    )
   
    validator_revenue /= constants.gwei  # Convert from Gwei to ETH
    validator_revenue *= eth_price  # Convert from ETH to Dollars

    # Calculate the profit per validator type
    validator_profit = validator_revenue - validator_costs

    # Calculate the revenue yields per validator type
    validator_revenue_yields = validator_revenue / (validator_eth_staked * eth_price)
    validator_revenue_yields *= constants.epochs_per_year / dt  # Annualize value

    # Calculate the profit yields per validator type
    validator_profit_yields = validator_profit / (validator_eth_staked * eth_price)
    validator_profit_yields *= constants.epochs_per_year / dt  # Annualize value

    # Calculate the total network revenue
    total_revenue = validator_revenue.sum(axis=0)

    # Calculate the total network profit
    total_profit = total_revenue - total_network_costs

    # Calculate the total network revenue yields
    total_revenue_yields = total_revenue / (eth_staked * eth_price)
    total_revenue_yields *= constants.epochs_per_year / dt  # Annualize value

    # Calculate the total network profit yields
    total_profit_yields = total_profit / (eth_staked * eth_price)
    total_profit_yields *= constants.epochs_per_year / dt  # Annualize value


    # Calculate yields for stakers using shared validators via pooling
    number_of_shared_validators = previous_state["number_of_shared_validators"]  
    number_of_stakers = validator_count_distribution - number_of_shared_validators
    ratio = number_of_stakers / validator_count_distribution
    staker_profit_yields = validator_profit / ((validator_eth_staked * ratio) * eth_price)
    staker_profit_yields *= constants.epochs_per_year / dt  # Annualize value


    return {
        # Per validator type
        "validator_eth_staked": validator_eth_staked,
        "validator_revenue": validator_revenue,
        "validator_profit": validator_profit,
        "validator_revenue_yields": validator_revenue_yields,
        "validator_profit_yields": validator_profit_yields,
        "staker_profit_yields": staker_profit_yields,
        # Aggregate
        "total_revenue": total_revenue,
        "total_profit": total_profit,
        "total_revenue_yields": total_revenue_yields,
        "total_profit_yields": total_profit_yields,
    }



def policy_validator_pooled_returns(
    params, substep, state_history, previous_state
    ) -> typing.Dict[str, any]:
    """
    ## Validator Pooled Returns Policy Function
    A compounding mechanism to calculate new validator instances created by pooling returns in staking pools
    as described in extension #5 of the model roadmap.
    """

    # Parameters
    avg_pool_size = params["avg_pool_size"] 
    pool_validator_indeces = params["pool_validator_indeces"]

    # State Variables
    eth_price = previous_state["eth_price"]
    validator_profit = previous_state["validator_profit"] # (USD)
    validator_pools_profits_eth = previous_state["validator_pools_profits"] 
    validator_count_distribution = previous_state["validator_count_distribution"]
    shared_validator_instances = previous_state["shared_validator_instances"]
    number_of_shared_validators = previous_state["number_of_shared_validators"]

    # Constants & function variables
    stake_requirement = constants.eth_deposited_per_validator
    new_shared_validators = shared_validator_instances * 0 # reset to zero


    if (avg_pool_size is not None and avg_pool_size > 0):
                
        for i in pool_validator_indeces: 
            assert (avg_pool_size < validator_count_distribution[i]) # pool size cannot be larger than the current validator count
        
            # Calculate new shared validator instances initialized via pool compounding
            number_of_pools_in_environment = np.round(validator_count_distribution[i] / avg_pool_size)
            validator_pools_profits_eth[i] += validator_profit[i] / eth_price # Aggregrate existing profits, convert from USD to ETH 
            avg_pool_profit = validator_pools_profits_eth[i] / number_of_pools_in_environment
            number_of_shared_validators_per_pool = np.floor(avg_pool_profit / stake_requirement).astype(int) # Calculate new shared validators initialized by pool
            new_shared_validators[i] = (number_of_pools_in_environment * number_of_shared_validators_per_pool) # Aggregrate according to number of pools
            validator_pools_profits_eth[i] -= new_shared_validators[i] * stake_requirement # Subtract the staked ammount from the accumulated profits
            
        number_of_shared_validators += new_shared_validators 
           
    return {
        "validator_pools_profits": validator_pools_profits_eth,
        "shared_validator_instances": new_shared_validators,
        "number_of_shared_validators": number_of_shared_validators
    }
    

def policy_total_online_validator_rewards(
    params, substep, state_history, previous_state
) -> typing.Dict[str, Gwei]:
    """
    ## Total Online Validator Rewards Policy Function
    Calculate the aggregate total online validator rewards.
    """
    # State Variables
    validating_rewards = previous_state["validating_rewards"]
    validating_penalties = previous_state["validating_penalties"]
    whistleblower_rewards = previous_state["whistleblower_rewards"]
    total_priority_fee_to_validators = previous_state[
        "total_priority_fee_to_validators"
    ]
    total_realized_mev_to_validators = previous_state[
        "total_realized_mev_to_validators"
    ]

    # Calculate total rewards for online validators
    total_online_validator_rewards = (
        validating_rewards
        - validating_penalties
        + whistleblower_rewards
        + total_priority_fee_to_validators
        + total_realized_mev_to_validators * constants.gwei
    )

    return {"total_online_validator_rewards": total_online_validator_rewards}


def update_supply_inflation(
    params, substep, state_history, previous_state, policy_input
) -> typing.Tuple[str, Percentage]:
    """
    ## Supply Inflation State Update Function
    Update the annualized ETH supply inflation.
    """
    # Policy Inputs
    network_issuance = policy_input["network_issuance"]

    # Parameters
    dt = params["dt"]

    # State Variables
    eth_supply = previous_state["eth_supply"]

    # Calculate the ETH supply inflation
    supply_inflation = network_issuance / eth_supply
    supply_inflation *= constants.epochs_per_year / dt  # Annualize value

    return "supply_inflation", supply_inflation
