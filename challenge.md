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
5. Git clone de volgende repository [https://gitlab.com/hu-hbo-ict/ti/openhaardvuur.git](https://gitlab.com/hu-hbo-ict/ti/openhaardvuur.git) om de software voor het haardvuur te gebruiken.
6. Flash de /pico folder naar je Raspberry Pi Pico en geniet! **Tip**: vergeet de ssd1309.py driver niet te flashen. De .mono bestanden moeten ook in een subfolder /px128w564h op de Raspberry Pi Pico geplaatst worden.
7. Heb je interesse in de combinatie van software & hardware ontwikkeling overweeg dan de richting Technische Informatica. Schrijf je in voor een specialisatie: [https://osiris.hu.nl/](https://osiris.hu.nl/)
