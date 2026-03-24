"""Tests for utility functions"""

import datetime

import pytest

from app.utils import campaign_year, campaign_label, campaign_months


class TestCampaignYear:
    """Tests for campaign_year function"""

    def test_campaign_year_january(self):
        """Test that January (month < 4) returns previous year"""
        date = datetime.date(2023, 1, 15)
        assert campaign_year(date) == 2022

    def test_campaign_year_march(self):
        """Test that March (month < 4) returns previous year"""
        date = datetime.date(2023, 3, 31)
        assert campaign_year(date) == 2022

    def test_campaign_year_april(self):
        """Test that April (month >= 4) returns current year"""
        date = datetime.date(2023, 4, 1)
        assert campaign_year(date) == 2023

    def test_campaign_year_december(self):
        """Test that December (month >= 4) returns current year"""
        date = datetime.date(2023, 12, 25)
        assert campaign_year(date) == 2023

    def test_campaign_year_boundary(self):
        """Test campaign year boundaries"""
        # Feb 2022 -> campaign 2021
        assert campaign_year(datetime.date(2022, 2, 1)) == 2021
        # Apr 2022 -> campaign 2022
        assert campaign_year(datetime.date(2022, 4, 1)) == 2022
        # Mar 2022 -> campaign 2021
        assert campaign_year(datetime.date(2022, 3, 31)) == 2021


class TestCampaignLabel:
    """Tests for campaign_label function"""

    def test_campaign_label_format(self):
        """Test that campaign_label formats correctly"""
        assert campaign_label(2022) == "2022/23"
        assert campaign_label(2023) == "2023/24"
        assert campaign_label(2024) == "2024/25"

    def test_campaign_label_year_across_century(self):
        """Test campaign label across century boundaries"""
        assert campaign_label(1999) == "1999/00"
        assert campaign_label(2000) == "2000/01"


class TestCampaignMonths:
    """Tests for campaign_months function"""

    def test_campaign_months_format(self):
        """Test that campaign_months returns correct month range"""
        assert campaign_months(2022) == "Abril 2022 - Marzo 2023"
        assert campaign_months(2023) == "Abril 2023 - Marzo 2024"

    def test_campaign_months_includes_years(self):
        """Test that both years are included in the output"""
        result = campaign_months(2020)
        assert "2020" in result
        assert "2021" in result

    def test_campaign_months_contains_months(self):
        """Test that both month names are present"""
        result = campaign_months(2022)
        assert "Abril" in result
        assert "Marzo" in result

    def test_campaign_months_range_across_years(self):
        """Test campaign month range spans across years correctly"""
        result = campaign_months(2022)
        # Should be: "Abril 2022 - Marzo 2023"
        parts = result.split(" - ")
        assert len(parts) == 2
        assert "2022" in parts[0]
        assert "2023" in parts[1]


class TestCampaignIntegration:
    """Integration tests for campaign functions"""

    def test_date_to_campaign_to_label(self):
        """Test the full chain: date -> campaign_year -> campaign_label"""
        # December 2022 -> campaign 2022 -> "2022/23"
        date = datetime.date(2022, 12, 15)
        cy = campaign_year(date)
        label = campaign_label(cy)
        assert label == "2022/23"

    def test_campaign_year_and_months_alignment(self):
        """Test that campaign_year and campaign_months are aligned"""
        date = datetime.date(2022, 7, 1)
        cy = campaign_year(date)
        months = campaign_months(cy)

        # July 2022 -> campaign 2022
        assert cy == 2022
        # Campaign 2022 -> Apr 2022 - Mar 2023
        assert "Abril 2022 - Marzo 2023" == months

    def test_campaign_year_april_boundary(self):
        """Test April 1st is start of new campaign"""
        march_31 = datetime.date(2023, 3, 31)
        april_1 = datetime.date(2023, 4, 1)

        march_campaign = campaign_year(march_31)
        april_campaign = campaign_year(april_1)

        # Mar 31 -> campaign 2022
        assert march_campaign == 2022
        # Apr 1 -> campaign 2023
        assert april_campaign == 2023

        months_2022 = campaign_months(march_campaign)
        months_2023 = campaign_months(april_campaign)

        assert "Marzo 2023" in months_2022
        assert "Abril 2023 - Marzo 2024" == months_2023
