# OpenHaardVuur

> Hogeschool Utrecht
> Instituut voor ICT
> Technische Informatica

Kerst project: open haard vuur animatie op een OLED display.

## Stappenplan

Wil je tijdens de kerstdagen naast een knapperend haardvuur doorbrengen? Verzamel dan de Technisch Informatica gadget door de volgende stappen te volgen:

1. Zoek in de [Turing Lab Hardware Shop](https://hu-hbo-ict.gitlab.io/turing-lab/ti-lab-shop/index.html) een OLED I2C display van 128x64 pixels met een SSD1306 chip. **Tip**: deze kan je ergens in la 9 vinden.
2. Ga naar het Turing Lab (HL15-4.060) en haal dit component op uit onze fysieke Turing Lab Hardware Shop. Dit component kan je meenemen zolang de voorraad strekt! 
3. Print je Kerst schouw op een van de 3D printers in het Turing Lab. Een [3D model in stl](./files/haard3D/TI_haard_v5.stl) is al voor je gemaakt. Plaatst dit op een USB stick en zet je printje aan. **Tip**: Dit kan alleen wanneer het lab open is.
4. Monteer je display in de schouw en sluit je Raspberry Pi Pico (of Pico W) aan volgens het [schema](README.md#hardware-setup).
5. Git clone de volgende repository [https://gitlab.com/hu-hbo-ict/ti/openhaardvuur.git](https://gitlab.com/hu-hbo-ict/ti/openhaardvuur.git).
6. Flash (met PyCharm of Thonny) de openhaardvuur/pico Kerst editie naar je Raspberry Pi Pico W en geniet! **Tip**: vergeet naast de main.py niet de ssd1309.py driver en de map met video beelden te flashen.
7. Heb je interesse in de combinatie van software & hardware? Overweeg dan de richting **T**echnische **I**nformatica. **Schrijf je tijdig in**: [https://osiris.hu.nl/](https://osiris.hu.nl/)
